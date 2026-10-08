# Easy Windows

A window switcher for Hyprland. Every open window is a box in a row, tagged
with a home-row hint. Press the hint to jump to that window. Nothing is drawn
behind the boxes.

- **8 windows or fewer:** one row, one key each: `a s d f j k l ;`.
- **More than 8:** still one key each, always a single press. After the home
  row come the nearest keys: `g h`, then `w e r u i o q p t y`, then
  `n m v c b x z , . /`, then `1`–`0`. Extra windows wrap onto more rows of 8.
  Up to 40 windows (one per key); windows past that are not shown.
- `Tab` or the arrow keys move the highlight, `Return`
  focuses it, and `Esc` closes it. Clicking a box works too; clicking between
  the boxes closes it. Launching it again also closes it.
- The pill under the boxes shows the highlighted window's name and title.

## How it is built

The switcher is `easy_windows.py`, a standalone GTK4 + gtk4-layer-shell surface
drawn with cairo. It is not a Noctalia panel, because Noctalia always paints an
opaque card behind a plugin panel. The Noctalia plugin only adds a bar button
that launches the script.

Needs `python-gobject`, `gtk4` and `gtk4-layer-shell`, and Hyprland ≥ 0.52
(`hyprctl repl`).

## Bind it

`~/.config/hypr/hyprland.lua`:

```lua
hl.bind("SUPER + tab", hl.dsp.exec_cmd("/home/you/.local/share/noctalia/plugins/easy-windows/easy_windows.py"))
```

## Options

| Flag | Default | |
|---|---|---|
| `--keys` | `asdfjkl;ghweruioqptynmvcbxz,./1234567890` | Hint keys in priority order. Earlier keys go to earlier windows. One key per window, so the count is also the window cap. |
| `--order` | `stable` | `stable`: creation order, so a window keeps its hint until a window opens or closes. `workspace`: by workspace, then position. `recent`: most recently focused first. |
| `--focused-last` | off | Move the window you're already in to the end. Hints then change with focus. |
| `--selftest` | | Runs the hint / layout / ordering checks and exits. |

Colours and box sizes are constants at the top of `easy_windows.py`; they do
not follow the Noctalia palette.

## Files

```
easy_windows.py      the switcher: window list, hints, drawing, focusing
plugin.toml          manifest: bar button only
widget.luau          bar button that launches easy_windows.py
translations/en.json
```
