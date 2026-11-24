# Group Spaces

A [herdr](https://herdr.dev) plugin that groups your Spaces by project and puts a header on each group.

- Spaces whose first pane is inside the same git repo are grouped together (worktrees count as their main repo).
- Spaces outside a git repo are grouped by folder. Spaces in your home folder are each their own group, even when two share a name.
- Groups are ordered by their most urgent Space: blocked, working, done, idle (or A-Z by name, see below). Inside a group, the same status order applies.
- The first Space of each group gets a `$group` token holding the project name.

It runs on herdr startup and whenever a Space or pane opens/closes, a Space is renamed, pane focus moves, or an agent changes status. No background process.

Requires herdr 0.9.5+, `python3` and `git`. Linux and macOS.

## Quick start

1. Install the plugin:

   ```bash
   herdr plugin install Ars-Paulina/herdr-group-spaces
   ```

2. Show the group header. The plugin only sets the name; your sidebar layout decides where it appears. Add a `$group` row at the top of `[ui.sidebar.spaces]` in herdr's `config.toml`:

   ```toml
   [ui.sidebar.spaces]
   rows = [
     [{ token = "$group", fg = "#cba6f7", bold = true }],
     ["state_icon", "workspace"],
     ["branch", "git_status"],
   ]
   ```

   Spaces without the token skip that row, so the header shows once per group.

3. Optional: add keyboard shortcuts to the same `config.toml`:

   ```toml
   [[keys.command]]
   key = "prefix+alt+g"
   type = "plugin_action"
   command = "group-spaces.toggle"
   description = "toggle project groups"

   [[keys.command]]
   key = "prefix+alt+r"
   type = "plugin_action"
   command = "group-spaces.rename"
   description = "rename a project group"

   [[keys.command]]
   key = "prefix+alt+s"
   type = "plugin_action"
   command = "group-spaces.sort"
   description = "toggle group order (status / A-Z)"
   ```

4. Apply the config and group your Spaces right away:

   ```bash
   herdr server reload-config
   herdr plugin action invoke group-spaces.apply
   ```

From then on it keeps itself up to date.

## How to use

| What | Shortcut (from step 3) | Action name | Command |
|---|---|---|---|
| Switch between project groups and a plain status-sorted list | `prefix+alt+g` | Toggle project groups | `herdr plugin action invoke group-spaces.toggle` |
| Switch group order between most urgent first and A-Z by name | `prefix+alt+s` | Toggle group order (status / A-Z) | `herdr plugin action invoke group-spaces.sort` |
| Rename a group | `prefix+alt+r` | Rename a project group | `herdr plugin action invoke group-spaces.rename` |
| Re-group now (e.g. right after `cd`-ing into another repo) | — | Re-group Spaces now | `herdr plugin action invoke group-spaces.apply` |

### Toggle the view

- **Project view** (default): groups with headers, as described above.
- **Plain view**: no headers, every Space sorted by status only.

Toggle again to switch back. Your choice is remembered across restarts.

### Sort groups A-Z

Toggle group order switches the project view between "most urgent group first" (default) and alphabetical by group name (renames count, case ignored). Spaces inside each group stay sorted by status. Your choice is remembered across restarts.

### Rename a group

1. Press `prefix+alt+r` (or run the action). A popup lists your groups with numbers.
2. Type the group's number and press Enter.
3. Type the new name and press Enter. Leave it empty to go back to the default name.
4. Choose whether to keep the name after the group closes:
   - **Y** (or Enter): kept. The next Space you open in that repo or folder gets the name again.
   - **n**: one-time. The rename is dropped once the group is gone.

Notes:

- Spaces in your home folder are renamed by their Space name, so a new Space with the same name (e.g. `~`) gets the rename too.
- Renaming only works in the project view.
- Renames are saved in `aliases.json` in the folder shown by `herdr plugin config-dir group-spaces`, so they survive plugin updates. You can edit that file by hand.

## Update

```bash
herdr plugin update group-spaces
```

## Uninstall

Clear the headers first (run from the plugin folder shown by `herdr plugin list`), then uninstall:

```bash
python3 group_spaces.py --clear
herdr plugin uninstall group-spaces
```

Then remove the `$group` row and the shortcuts from your `config.toml`.

## Limits

- herdr does not run plugin hooks when a pane changes directory, so a `cd` into another repo is picked up the next time focus moves (or any other event), or with a manual re-group.
- Project = the first pane of the Space. Spaces with panes in several repos follow that first pane.

## Development

Self-check: `python3 group_spaces.py --test`.
