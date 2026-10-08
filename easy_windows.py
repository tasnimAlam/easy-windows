#!/usr/bin/env python3
"""Window switcher for Hyprland with easymotion-style home-row hints.

Every mapped window is a box in a row, tagged with a hint. Nothing is drawn
behind the boxes. Runs as its own layer-shell surface (GTK4 + gtk4-layer-shell)
because a Noctalia panel always paints an opaque card behind its content.

  hint key        focus that window
  Tab / arrows    move the highlight     Return      focus the highlight
  Escape          close                  launching it again also closes it
"""

import argparse
import json
import math
import re
import subprocess
import sys

BOX_W, BOX_H = 104, 116  # one window box
GAP = 10
PER_ROW = 8
FOOT_H = 30  # pill under the boxes with the highlighted window's title
MIN_W = 360
# home row first, then the keys nearest to it; one key per window, so this is the window cap
DEFAULT_KEYS = "asdfjkl;ghweruioqptynmvcbxz,./1234567890"

BOX = (0.13, 0.13, 0.16, 1)
ACCENT = (0.80, 0.65, 0.97)  # Catppuccin mauve; not read from the Noctalia palette
HINT = (1.0, 0.30, 0.30)
TEXT = (0.92, 0.92, 0.95)
MUTED = (0.62, 0.62, 0.68)

# Lua for `hyprctl repl`; the address is validated hex before it is formatted in.
FOCUS_LUA = (
    "local w = hl.get_window([==[address:%s]==]) "
    "if w then hl.dispatch(hl.dsp.focus({ window = w })) end"
)


# pure logic ------------------------------------------------------------------


def parse_keys(spec):
    """"asdfjkl;" -> ["a", "s", ...]; drops duplicates and non-printables."""
    keys = []
    for ch in spec.lower():
        if ch.isprintable() and not ch.isspace() and ch not in keys:
            keys.append(ch)
    return keys if len(keys) >= 2 else parse_keys(DEFAULT_KEYS)


def assign(n, keys):
    """n hints, one key each; never more than len(keys)."""
    return keys[:n]


def match(typed, hints):
    """("exact", index) | ("prefix", first matching index) | ("none", None)"""
    first = None
    for i, h in enumerate(hints):
        if h == typed:
            return "exact", i
        if first is None and h.startswith(typed):
            first = i
    return ("prefix", first) if first is not None else ("none", None)


def row_rects(n):
    """(width, height, [(x, y)]): boxes in rows of PER_ROW, each row centred."""
    rows = max(1, math.ceil(n / PER_ROW))
    width = max(MIN_W, min(n, PER_ROW) * (BOX_W + GAP) - GAP)
    rects = []
    for i in range(n):
        r = i // PER_ROW
        k = min(PER_ROW, n - r * PER_ROW)  # boxes in this row
        x0 = (width - (k * (BOX_W + GAP) - GAP)) / 2
        rects.append((x0 + (i % PER_ROW) * (BOX_W + GAP), r * (BOX_H + GAP)))
    return width, rows * (BOX_H + GAP) + FOOT_H, rects


def rect_at(x, y, rects):
    for i, (bx, by) in enumerate(rects):
        if bx <= x <= bx + BOX_W and by <= y <= by + BOX_H:
            return i
    return None


def sort_windows(clients, order, focused_last):
    wins = [
        c
        for c in clients
        if c.get("mapped", True)
        and not c.get("hidden")
        and re.fullmatch(r"0x[0-9a-f]+", c.get("address", ""))
    ]
    if order == "recent":
        wins.sort(key=lambda c: c.get("focusHistoryID", 1e9))
    elif order == "stable":
        # stableId grows with each window Hyprland creates and never changes, so
        # a window keeps its hint until some window opens or closes
        wins.sort(key=lambda c: int(c.get("stableId") or "0", 16))
    else:

        def key(c):
            ws = c.get("workspace", {}).get("id", 1e9)
            # special workspaces (negative ids) go after the regular ones
            return (ws if ws >= 0 else 1e8 - ws, *c.get("at", (0, 0)))

        wins.sort(key=key)
    if focused_last:
        for i, c in enumerate(wins):
            if c.get("focusHistoryID") == 0:
                wins.append(wins.pop(i))
                break
    return wins


def selftest():
    keys = parse_keys("asdfjkl;")
    assert assign(3, keys) == ["a", "s", "d"]
    assert assign(99, keys) == keys  # capped: one key per window, no prefixes
    assert match(";", assign(8, keys)) == ("exact", 7)
    assert match("x", assign(8, keys)) == ("none", None)
    default = parse_keys(DEFAULT_KEYS)
    assert len(default) == len(DEFAULT_KEYS) == 40  # no duplicate keys
    assert assign(10, default)[8:] == ["g", "h"]  # near keys follow the home row

    w, h, r = row_rects(3)
    assert (w, h) == (MIN_W, BOX_H + GAP + FOOT_H) and r[0][0] == (MIN_W - 332) / 2
    assert rect_at(r[1][0] + 5, 5, r) == 1 and rect_at(r[1][0] - 5, 5, r) is None
    w, h, r = row_rects(11)  # 8 on the first row, 3 centred on the second
    assert w == 8 * BOX_W + 7 * GAP and h == 2 * (BOX_H + GAP) + FOOT_H
    assert r[7] == (w - BOX_W, 0) and r[8][1] == BOX_H + GAP and r[8][0] > 0
    assert rect_at(r[10][0] + 1, r[10][1] + 1, r) == 10
    assert row_rects(0)[2] == []

    wins = sort_windows(
        [
            {"address": "0x1", "workspace": {"id": 2}, "at": [0, 0], "focusHistoryID": 0},
            {"address": "0x2", "workspace": {"id": 1}, "at": [5, 0], "focusHistoryID": 1},
            {"address": "0x3", "workspace": {"id": -98}, "at": [0, 0], "focusHistoryID": 2},
            {"address": "0x4", "workspace": {"id": 3}, "at": [0, 0], "focusHistoryID": 3},
            {"address": "bad; rm -rf", "workspace": {"id": 1}},
            {"address": "0x5", "workspace": {"id": 1}, "mapped": False},
        ],
        "workspace",
        True,
    )
    assert [w["address"] for w in wins] == ["0x2", "0x4", "0x3", "0x1"], wins
    # stable order ignores focus, workspace and position
    a = [{"address": "0x1", "stableId": "1800000a", "focusHistoryID": 0, "at": [9, 9]},
         {"address": "0x2", "stableId": "18000007", "focusHistoryID": 1, "at": [0, 0]}]
    b = [dict(a[1], focusHistoryID=0, at=[5, 5]), dict(a[0], focusHistoryID=1, workspace={"id": 3})]
    assert [w["address"] for w in sort_windows(a, "stable", False)] == ["0x2", "0x1"]
    assert [w["address"] for w in sort_windows(b, "stable", False)] == ["0x2", "0x1"]
    print("ok")


if "--selftest" in sys.argv:
    selftest()
    sys.exit(0)


# ui --------------------------------------------------------------------------

from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")  # must be loaded before libwayland-client

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GioUnix, GLib, Graphene, Gtk, Pango, PangoCairo
from gi.repository import Gtk4LayerShell as LayerShell


def short_name(cls, title):
    return cls.split(".")[-1] or title or "?"


def icon_for(theme, cls, size, scale):
    """Paintable for a window class, via its .desktop entry where there is one."""
    for cand in dict.fromkeys((cls, cls.lower(), cls.split(".")[-1].lower())):
        try:
            icon = GioUnix.DesktopAppInfo.new(cand + ".desktop").get_icon()
        except (TypeError, AttributeError):  # no such desktop entry
            icon = None
        if icon:
            return theme.lookup_by_gicon(icon, size, scale, Gtk.TextDirection.NONE, 0)
        if theme.has_icon(cand):
            return theme.lookup_icon(cand, None, size, scale, Gtk.TextDirection.NONE, 0)
    return theme.lookup_icon(
        "application-x-executable", None, size, scale, Gtk.TextDirection.NONE, 0
    )


def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


class Row(Gtk.Widget):
    def __init__(self, windows, hints):
        super().__init__()
        self.windows = windows
        self.hints = hints
        self.typed = ""
        self.selected = 0
        self.icons = {}
        width, height, self.rects = row_rects(len(windows))
        self.size = (width, height)
        self.set_size_request(width, height)

    def index_at(self, x, y):
        return rect_at(x, y, self.rects)

    def live(self, i):
        return self.hints[i].startswith(self.typed)

    def text(self, cr, markup, size, bold=False, width=None):
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string("sans")
        font.set_absolute_size(size * Pango.SCALE)
        if bold:
            font.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(font)
        if width:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_markup(markup)
        return layout, *layout.get_pixel_size()

    # hint with the part already typed faded
    def hint_markup(self, i):
        label = self.hints[i]
        done = len(self.typed) if self.live(i) else 0
        return '<span alpha="45%%">%s</span>%s' % (
            GLib.markup_escape_text(label[:done]),
            GLib.markup_escape_text(label[done:]),
        )

    # icons: [(window index, x, y, side)]
    def paint_icons(self, snap, icons):
        scale = self.get_scale_factor()
        theme = Gtk.IconTheme.get_for_display(self.get_display())
        for i, x, y, s in icons:
            cls = self.windows[i]["class"]
            if cls not in self.icons:
                self.icons[cls] = icon_for(theme, cls, 48, scale)
            snap.save()
            snap.translate(Graphene.Point().init(x, y))
            snap.push_opacity(1 if self.live(i) else 0.25)
            self.icons[cls].snapshot(snap, s, s)
            snap.pop()
            snap.restore()

    def do_snapshot(self, snap):
        width, height = self.size
        cr = snap.append_cairo(Graphene.Rect().init(0, 0, width, height))
        icons = []
        for i, (x, y) in enumerate(self.rects):
            live = self.live(i)
            # text leaves a current point that cairo's arc() would draw a line from
            cr.new_path()
            rounded_rect(cr, x + 1, y + 1, BOX_W - 2, BOX_H - 2, 12)
            cr.set_source_rgba(*BOX[:3], 1 if live else 0.45)
            cr.fill_preserve()
            if i == self.selected:
                cr.set_source_rgba(*ACCENT, 0.2)
                cr.fill_preserve()
                cr.set_source_rgb(*ACCENT)
                cr.set_line_width(2)
                cr.stroke()
            cr.new_path()
            icons.append((i, x + (BOX_W - 44) / 2, y + 14, 44))

            name = GLib.markup_escape_text(self.windows[i]["name"])
            layout, _tw, _th = self.text(cr, name, 11, width=BOX_W - 12)
            cr.move_to(x + 6, y + 64)
            cr.set_source_rgba(*MUTED, 1 if live else 0.4)
            PangoCairo.show_layout(cr, layout)

            layout, tw, _th = self.text(cr, self.hint_markup(i), 17, bold=True)
            cr.move_to(x + (BOX_W - tw) / 2, y + 84)
            cr.set_source_rgba(*(HINT if live else MUTED), 1 if live else 0.35)
            PangoCairo.show_layout(cr, layout)

        # which window is highlighted, on a pill of its own
        if self.windows:
            w = self.windows[self.selected]
            foot = "<b>%s</b>   %s" % tuple(GLib.markup_escape_text(w[k]) for k in ("name", "title"))
            if self.typed:
                foot = GLib.markup_escape_text(self.typed + " …   ") + foot
        else:
            foot = "No open windows"
        layout, _tw, th = self.text(cr, foot, 12, width=width - 24)
        cr.new_path()
        rounded_rect(cr, 0, height - FOOT_H, width, FOOT_H, FOOT_H / 2)
        cr.set_source_rgba(*BOX)
        cr.fill()
        cr.move_to(12, height - FOOT_H + (FOOT_H - th) / 2)
        cr.set_source_rgb(*TEXT)
        PangoCairo.show_layout(cr, layout)

        self.paint_icons(snap, icons)


class App(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id="io.github.tasnimalam.EasyWindows")
        self.args = args
        self.views = []  # one per monitor, kept in step by update()

    @property
    def view(self):
        return self.views[0]

    def do_activate(self):
        if self.get_windows():  # a second launch toggles it off
            self.quit()
            return

        keys = parse_keys(self.args.keys)
        out = subprocess.run(
            ["hyprctl", "-j", "clients"], capture_output=True, text=True, check=True
        ).stdout
        wins = sort_windows(json.loads(out), self.args.order, self.args.focused_last)
        wins = wins[: len(keys)]
        for w in wins:
            w["class"] = w.get("class") or w.get("initialClass") or ""
            w["title"] = w.get("title") or ""
            w["name"] = short_name(w["class"], w["title"])

        hints = assign(len(wins), keys)
        display = Gdk.Display.get_default()
        css = Gtk.CssProvider()
        css.load_from_string("window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # the same switcher on every monitor; keys go to whichever has focus
        for monitor in display.get_monitors():
            view = Row(wins, hints)
            self.views.append(view)
            win = Gtk.ApplicationWindow(application=self, child=view)
            win.set_default_size(*view.size)

            LayerShell.init_for_window(win)
            LayerShell.set_namespace(win, "easy-windows")
            LayerShell.set_monitor(win, monitor)
            LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
            LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.EXCLUSIVE)

            keyc = Gtk.EventControllerKey()
            keyc.connect("key-pressed", self.on_key)
            win.add_controller(keyc)
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", self.on_motion)
            view.add_controller(motion)
            click = Gtk.GestureClick()
            click.connect("released", self.on_click)
            view.add_controller(click)

            win.present()

    def focus(self, index):
        view = self.view
        if not 0 <= index < len(view.windows):
            return
        addr = view.windows[index]["address"]
        self.hold()
        for win in self.get_windows():
            win.destroy()
        # Let the layer surface give keyboard focus back before focusing.
        GLib.timeout_add(40, self.dispatch, addr)

    def dispatch(self, addr):
        subprocess.run(["hyprctl", "repl", FOCUS_LUA % addr], capture_output=True)
        self.release()
        return False

    def update(self, typed=None, selected=None):
        for view in self.views:
            if typed is not None:
                view.typed = typed
            if selected is not None:
                view.selected = selected
            view.queue_draw()

    def select(self, index):
        if index is not None and index != self.view.selected:
            self.update(selected=index)

    def on_key(self, _ctrl, keyval, _code, _state):
        view = self.view
        n = len(view.windows)
        if keyval == Gdk.KEY_Escape:
            self.quit()
        elif keyval == Gdk.KEY_BackSpace:
            self.update(typed=view.typed[:-1])
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.focus(view.selected)
        elif keyval in (Gdk.KEY_Tab, Gdk.KEY_Right, Gdk.KEY_Down) and n:
            self.select((view.selected + 1) % n)
        elif keyval in (Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Left, Gdk.KEY_Up) and n:
            self.select((view.selected - 1) % n)
        else:
            ch = chr(Gdk.keyval_to_unicode(Gdk.keyval_to_lower(keyval)))
            if ch == "\0" or not n:
                return True
            result, index = match(view.typed + ch, view.hints)
            if result == "exact":
                self.focus(index)
            elif result == "prefix":
                self.update(typed=view.typed + ch, selected=index)
            elif view.typed:
                # dead end: start over, so a mistyped prefix costs one press
                self.update(typed="")
        return True

    def on_motion(self, _ctrl, x, y):
        self.select(self.view.index_at(x, y))

    def on_click(self, _gesture, _n, x, y):
        index = self.view.index_at(x, y)
        if index is None:
            self.quit()
        else:
            self.focus(index)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--keys", default=DEFAULT_KEYS, help="hint keys, in priority order")
    p.add_argument("--order", choices=("stable", "workspace", "recent"), default="stable")
    p.add_argument("--focused-last", action="store_true", help="move the focused window to the end")
    p.add_argument("--selftest", action="store_true", help="run the logic checks and exit")
    args = p.parse_args()
    App(args).run(None)


if __name__ == "__main__":
    main()
