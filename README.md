# Group Spaces

A [herdr](https://herdr.dev) plugin that groups your Spaces by project and puts a header on each group.

- Spaces whose first pane is inside the same git repo are grouped together (worktrees count as their main repo).
- Spaces outside a git repo are each their own group, even when two share a name.
- Groups are ordered by their most urgent Space: blocked, working, done, idle. Inside a group, the same order applies.
- The first Space of each group gets a `$group` token holding the project name.

It runs on herdr startup and whenever a Space or pane opens/closes, a Space is renamed, or an agent changes status. No background process.

## Install

```bash
herdr plugin install <owner>/<repo>
```

Requires herdr 0.9.5+, `python3` and `git`. Linux and macOS.

## Show the header

The plugin only sets the value; your sidebar layout decides where it shows. Add a `$group` row at the top of `[ui.sidebar.spaces]` in herdr's `config.toml`:

```toml
[ui.sidebar.spaces]
rows = [
  [{ token = "$group", fg = "#cba6f7", bold = true }],
  ["state_icon", "workspace"],
  ["branch", "git_status"],
]
```

Then run `herdr server reload-config`. Spaces without the token skip that row, so the header appears once per group.

## Use

- Re-group by hand (for example after `cd`-ing a pane into another repo): run the **Re-group Spaces now** action, or `herdr plugin action invoke group-spaces.apply`.
- Self-check: `python3 group_spaces.py --test`.

## Uninstall

Clear the headers first (run from the plugin folder shown by `herdr plugin list`), then uninstall:

```bash
python3 group_spaces.py --clear
herdr plugin uninstall group-spaces
```

## Limits

- A pane changing directory is not a herdr event, so a `cd` into another repo is picked up on the next event or a manual re-group.
- Project = the first pane of the Space. Spaces with panes in several repos follow that first pane.
