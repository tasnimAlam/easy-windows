# Easy Windows

Window switcher for Hyprland with easymotion-style home-row hints. Every mapped
window is a box in a row; pressing its hint focuses it. Nothing is drawn behind
the boxes. Shown on every monitor at once.

## Layout

- This folder is the source. Noctalia loads it through a symlink:
  `~/.local/share/noctalia/plugins/easy-windows -> ~/Documents/easy-windows`.
- `easy_windows.py`: the whole switcher. Standalone GTK4 + `gtk4-layer-shell`
  overlay drawn with cairo (window list, hints, drawing, keys, focusing).
- `plugin.toml`, `widget.luau`, `translations/en.json`: Noctalia plugin
  `tasnimAlam/easy-windows`. It is only a bar button that launches the script.
- `SUPER+Tab` is bound in `~/.config/hypr/hyprland.lua` (around line 281) to
  `/home/shourov/.local/share/noctalia/plugins/easy-windows/easy_windows.py`.

## Run and test

```fish
./easy_windows.py              # open; running it again closes it (single instance)
./easy_windows.py --selftest   # hint assignment, row geometry, hit-test, ordering
./easy_windows.py --help       # --keys, --order stable|workspace|recent, --focused-last
```

If an instance gets stuck holding the keyboard, kill it by pid; `pkill -f
easy_windows.py` from a shell whose own command line contains that text kills
the shell too.

After editing `plugin.toml`: `noctalia msg plugins disable tasnimAlam/easy-windows`
then `enable`. `noctalia msg config-reload` alone keeps stale manifest values.

## Behaviour to preserve

- Hints: always one key per window, never a two-key prefix. Capacity is the
  number of keys; windows past it are not shown. Default `DEFAULT_KEYS` is the
  home row, then the nearest keys, then digits (40).
- Default order is `stable`: sorted by Hyprland's `stableId` (hex, grows per
  created window), so hints do not change with focus, workspace or position.
- Hints are plain red letters with no pill. The typed part of a hint is faded;
  non-matching boxes are dimmed.
- Rows of 8 full-size boxes, each row centred; the surface sizes to its content.
- A pill under the boxes shows the highlighted window's name and title.
- One layer-shell window per monitor; `App.update()` keeps typed prefix and
  highlight in step across them.
- Focus: destroy the windows, wait 40 ms so the layer gives keyboard focus
  back, then `hyprctl repl` with `hl.dispatch(hl.dsp.focus({ window = w }))`.
  The address is validated as hex before it goes into the Lua string.

## Facts that cost time to learn

- Environment: Hyprland 0.56 (Lua config, `hyprctl repl`), Noctalia 5.2.1.
- A Noctalia plugin panel always paints an opaque card behind its content.
  There is no manifest key or API to remove it (checked in Noctalia's source).
  That is why this is a GTK overlay and not a Noctalia panel.
- Noctalia panel UI is flex rows/columns only: no absolute positioning, no
  shapes, and panels cannot resize at runtime.
- Noctalia's built-in `noctalia msg window-switcher` is Alt+Tab-style cycling
  with no hint keys.
- `gtk4-layer-shell` must be loaded before libwayland-client, hence the
  `CDLL("libgtk4-layer-shell.so")` before `import gi`.
- cairo: text drawing leaves a current point, and the next `arc()` draws a line
  from it. Call `cr.new_path()` before starting a new shape.
- Colours and sizes are constants at the top of `easy_windows.py`; they do not
  follow the Noctalia palette.
- A Hyprland layer rule for blur on this namespace (`easy-windows`) was tried on
  the earlier version and did not apply reliably; it was removed.

## Not yet verified on the real machine

- Choosing a window by hint key or click (the focus step) in the current version.
- The `SUPER+Tab` bind and the bar button firing.
- More than 4 windows live (two-row layout was only rendered offscreen).
- Monitors plugged in while the switcher is open (monitor list is read at launch).

## Before publishing

- `README.md` shows the bind with a `/home/you/...` placeholder path.
- No git repository yet.
