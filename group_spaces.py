#!/usr/bin/env python3
"""Group herdr Spaces by project, then sort by status inside each group.

Project = git repo of the space's first pane (worktrees count as their main repo).
Spaces outside a repo are each their own group, even when names repeat.
Groups are ordered by their most urgent space: blocked, working, done, idle, rest.
Ties keep their current order. The first space of each group gets a `$group`
metadata token with the project name; show it with a row in [ui.sidebar.spaces].

One-shot: herdr runs this on startup and on workspace/pane/agent events.
Run with --test for a self-check, --clear to remove all headers.
"""
import fcntl, json, os, socket, subprocess, sys

SOCK = os.environ.get("HERDR_SOCKET_PATH") or os.path.expanduser("~/.config/herdr/herdr.sock")
RANK = {"blocked": 0, "working": 1, "done": 2, "idle": 9}  # idle always last, below unknown (4)
SOURCE = "group-spaces"


def call(method, params=None):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5)
        s.connect(SOCK)
        s.sendall((json.dumps({"id": "gs", "method": method, "params": params or {}}) + "\n").encode())
        r = json.loads(s.makefile().readline())
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["result"]


def repo_of(cwd, _cache={}):
    """Repo name for a folder, or None when it is not inside a git repo."""
    if not cwd:
        return None
    if cwd not in _cache:
        try:
            common = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            common = ""
        if common:  # /repo/.git -> repo ; bare repo dir -> its own name
            root = os.path.dirname(common) if os.path.basename(common) == ".git" else common
            _cache[cwd] = os.path.basename(root.rstrip("/")) or root
        else:
            _cache[cwd] = None
    return _cache[cwd]


def plan(workspaces, panes, repo_of=repo_of):
    """Return (wanted workspace id order, {workspace_id: header name or None})."""
    cwd = {}
    for p in panes:  # first pane listed per workspace wins
        cwd.setdefault(p["workspace_id"], p.get("foreground_cwd") or p.get("cwd"))
    groups = {}  # insertion order -> ties keep current order
    for w in workspaces:
        repo = repo_of(cwd.get(w["workspace_id"]))
        key = ("repo", repo) if repo else ("space", w["workspace_id"])
        groups.setdefault(key, (repo or w.get("label") or "?", []))[1].append(w)
    rank = lambda w: RANK.get(w["agent_status"], 4)
    order, headers = [], {}
    for name, members in sorted(groups.values(), key=lambda g: min(map(rank, g[1]))):
        for i, w in enumerate(sorted(members, key=rank)):
            order.append(w["workspace_id"])
            headers[w["workspace_id"]] = name if i == 0 else None
    return order, headers


def apply(clear=False):
    ws = call("workspace.list")["workspaces"]
    order, headers = plan(ws, call("pane.list")["panes"])
    if clear:
        headers = dict.fromkeys(headers)
    elif order != [w["workspace_id"] for w in ws]:
        call("workspace.move_block", {"workspace_ids": order})
    for w in ws:  # only write tokens that differ, so idle runs cause no events
        want = headers.get(w["workspace_id"])
        if (w.get("tokens") or {}).get("group") != want:
            call("workspace.report_metadata",
                 {"workspace_id": w["workspace_id"], "source": SOURCE, "tokens": {"group": want}})


def test():
    repos = {"/x": "x", "/y": "y"}.get
    ws = [{"workspace_id": i, "label": l, "agent_status": s} for i, l, s in [
        ("a", "a", "idle"), ("b", "b", "working"), ("c", "c", "blocked"), ("d", "d", "done"),
        ("e", "~", "idle"), ("f", "~", "idle")]]
    panes = [{"workspace_id": i, "cwd": c} for i, c in
             [("a", "/x"), ("b", "/y"), ("c", "/x"), ("d", "/y"), ("e", "/n"), ("f", "/n")]]
    order, headers = plan(ws, panes, repos)
    assert order == ["c", "a", "b", "d", "e", "f"], order  # x holds the blocked one, so first
    assert headers == {"c": "x", "a": None, "b": "y", "d": None, "e": "~", "f": "~"}, headers
    print("ok")


def main():
    if "--test" in sys.argv:
        return test()
    lock_dir = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(lock_dir, "group-spaces.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # events come in bursts: run one at a time, each on fresh state
        apply(clear="--clear" in sys.argv)


if __name__ == "__main__":
    main()
