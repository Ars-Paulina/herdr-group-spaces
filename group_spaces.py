#!/usr/bin/env python3
"""Group herdr Spaces by project, then sort by status inside each group.

Project = git repo of the space's first pane (worktrees count as their main repo).
Spaces outside a repo group by folder; spaces in the home folder are each their own group.
Groups are ordered by their most urgent space: blocked, working, done, idle, rest.
Ties keep their current order. The first space of each group gets a `$group`
metadata token with the project name; show it with a row in [ui.sidebar.spaces].

Two views: "project" (above) and "status" (no groups: all spaces sorted by status).
Group names can be renamed; renames live in aliases.json in the plugin config dir.
Renames are keyed by repo name or folder path (home-folder spaces: by space name), so a
group that closes and opens again gets its name back. A rename saved with keep=false
is dropped once its group is gone.

One-shot: herdr runs this on startup and on workspace/pane/agent events.
Flags: --toggle (switch view), --rename (interactive, run in a popup),
--test (self-check), --clear (remove all headers).
"""
import fcntl, functools, json, os, socket, subprocess, sys

SOCK = os.environ.get("HERDR_SOCKET_PATH") or os.path.expanduser("~/.config/herdr/herdr.sock")
RANK = {"blocked": 0, "working": 1, "done": 2, "idle": 9}  # idle always last, below unknown (4)
SOURCE = "group-spaces"
HOME = os.path.normpath(os.path.expanduser("~"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("HERDR_PLUGIN_STATE_DIR") or HERE
CONFIG_DIR = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or HERE
MODE_FILE = os.path.join(STATE_DIR, "mode")
ALIAS_FILE = os.path.join(CONFIG_DIR, "aliases.json")


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(path + ".tmp", path)


def alias_name(v):
    """aliases.json values: "name" (kept) or {"name": "...", "keep": false} (dropped when the group closes)."""
    return v.get("name") if isinstance(v, dict) else v


def get_mode():
    return read_json(MODE_FILE, "project")


def call(method, params=None):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5)
        s.connect(SOCK)
        s.sendall((json.dumps({"id": "gs", "method": method, "params": params or {}}) + "\n").encode())
        r = json.loads(s.makefile().readline())
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["result"]


@functools.cache
def repo_of(cwd):
    """Repo name for a folder, or None when it is not inside a git repo."""
    if not cwd:
        return None
    try:
        common = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not common:
        return None
    # /repo/.git -> repo ; bare repo dir -> its own name
    root = os.path.dirname(common) if os.path.basename(common) == ".git" else common
    return os.path.basename(root) or root


def plan(workspaces, panes, repo_of=repo_of, aliases=None, mode="project"):
    """Return (wanted workspace id order, {workspace_id: header or None}, [(alias key, name, size)])."""
    aliases = aliases or {}
    rank = lambda w: RANK.get(w["agent_status"], 4)
    if mode == "status":  # plain view: no groups, just status order
        return [w["workspace_id"] for w in sorted(workspaces, key=rank)], {}, []
    cwd = {}
    for p in panes:  # first pane listed per workspace wins
        d = p.get("foreground_cwd") or p.get("cwd")
        cwd.setdefault(p["workspace_id"], d and os.path.normpath(d))  # one spelling per folder
    groups = {}  # insertion order -> ties keep current order
    for w in workspaces:
        d = cwd.get(w["workspace_id"])
        repo = repo_of(d)
        if repo:  # same repo (worktrees included) -> one group
            key, name = ("repo", repo), repo
        elif d and d != HOME:  # no repo: same folder -> one group
            key, name = ("dir", d), os.path.basename(d) or d
        else:  # home folder or unknown: every space is its own group, even with the same name
            key, name = ("space", w["workspace_id"]), w.get("label") or "?"
        # home-folder spaces are separate groups but are renamed by space name, so the name survives a new space
        akey = "name:" + name if key[0] == "space" else ":".join(key)
        groups.setdefault(key, (akey, alias_name(aliases.get(akey)) or name, []))[2].append(w)
    order, headers, listing = [], {}, []
    for akey, name, members in sorted(groups.values(), key=lambda g: min(map(rank, g[2]))):
        listing.append((akey, name, len(members)))
        for i, w in enumerate(sorted(members, key=rank)):
            order.append(w["workspace_id"])
            headers[w["workspace_id"]] = name if i == 0 else None
    return order, headers, listing


def state():
    ws = call("workspace.list")["workspaces"]
    return ws, plan(ws, call("pane.list")["panes"], aliases=read_json(ALIAS_FILE, {}), mode=get_mode())


def apply(clear=False):
    ws, (order, headers, listing) = state()
    if listing:  # project view: forget non-kept renames whose group has closed
        aliases, live = read_json(ALIAS_FILE, {}), {k for k, _, _ in listing}
        kept = {k: v for k, v in aliases.items() if k in live or isinstance(v, str)}
        if kept != aliases:
            write_json(ALIAS_FILE, kept)
    if clear:
        headers = {}
    elif order != [w["workspace_id"] for w in ws]:
        call("workspace.move_block", {"workspace_ids": order})
    for w in ws:  # only write tokens that differ, so idle runs cause no events
        want = headers.get(w["workspace_id"])
        if (w.get("tokens") or {}).get("group") != want:
            call("workspace.report_metadata",
                 {"workspace_id": w["workspace_id"], "source": SOURCE, "tokens": {"group": want}})


def rename():
    """Interactive: pick a group, type a new name (empty = back to the default).
    Returns (alias key, new value or None) to save, or None to change nothing."""
    if get_mode() != "project":
        input("Project view is off; toggle it on to rename groups. Press Enter to close.")
        return None
    _, (_, _, listing) = state()
    aliases = read_json(ALIAS_FILE, {})
    for i, (key, name, size) in enumerate(listing, 1):
        print(f"{i:>2}) {name}  ({size} space{'s' if size > 1 else ''}){'  *renamed' if key in aliases else ''}")
    pick = input("\nGroup number to rename (Enter = cancel): ").strip()
    if not pick.isdigit() or not 1 <= int(pick) <= len(listing):
        return None
    key = listing[int(pick) - 1][0]
    new = input("New name (Enter = default name): ").strip()
    if not new:
        return key, None
    keep = input("Keep this name after the group closes? [Y/n]: ").strip().lower() not in ("n", "no")
    return key, new if keep else {"name": new, "keep": False}


def test():
    repos = {"/x": "x", "/y": "y"}.get
    ws = [{"workspace_id": i, "label": l, "agent_status": s} for i, l, s in [
        ("a", "a", "idle"), ("b", "b", "working"), ("c", "c", "blocked"), ("d", "d", "done"),
        ("e", "~", "idle"), ("f", "~", "idle"), ("g", "PC", "idle"), ("h", "PC", "idle")]]
    panes = [{"workspace_id": i, "cwd": c} for i, c in
             [("a", "/x"), ("b", "/y"), ("c", "/x"), ("d", "/y"), ("e", HOME), ("f", HOME),
              ("g", "/p/PC"), ("h", "/p/PC/")]]
    order, headers, listing = plan(ws, panes, repos)
    assert order == ["c", "a", "b", "d", "e", "f", "g", "h"], order  # x holds the blocked one, so first
    assert headers == {"c": "x", "a": None, "b": "y", "d": None,
                       "e": "~", "f": "~",  # home: separate groups even with the same name
                       "g": "PC", "h": None}, headers  # same non-repo folder: one group
    _, headers, listing = plan(ws, panes, repos, aliases={
        "repo:x": "Main app", "dir:/p/PC": {"name": "My PC", "keep": False}, "name:~": "Home"})
    assert headers["c"] == "Main app" and headers["g"] == "My PC" and headers["b"] == "y", headers
    assert headers["e"] == headers["f"] == "Home", headers  # home spaces renamed by name, still 2 groups
    assert ("name:~", "Home", 1) in listing and listing.count(("name:~", "Home", 1)) == 2, listing
    order, headers, listing = plan(ws, panes, repos, mode="status")
    assert order == ["c", "b", "d", "a", "e", "f", "g", "h"] and headers == {} and listing == [], order
    print("ok")


def main():
    if "--test" in sys.argv:
        return test()
    change = rename() if "--rename" in sys.argv else None  # outside the lock: it waits for typing
    with open(os.path.join(STATE_DIR, "group-spaces.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # events come in bursts: run one at a time, each on fresh state
        if change:  # read fresh under the lock so a concurrent run's write is not lost
            aliases = {**read_json(ALIAS_FILE, {}), change[0]: change[1]}
            write_json(ALIAS_FILE, {k: v for k, v in aliases.items() if v})  # None = back to default
        if "--toggle" in sys.argv:
            write_json(MODE_FILE, "status" if get_mode() == "project" else "project")
        apply(clear="--clear" in sys.argv)


if __name__ == "__main__":
    main()
