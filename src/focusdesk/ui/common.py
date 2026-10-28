"""Utilitare UI comune: tema, fonturi, dialoguri simple, widgeturi reutilizabile."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

import ttkbootstrap as tb

from ..domain.models import CLOSED_STATUSES, Kind

if TYPE_CHECKING:
    from .app import FocusDeskApp

from .design import C, FONT, BASE, install, icon, button

# Compatibilité cu configurațiile vechi; randarea este exclusiv luminoasă.
THEMES = {"light": "bootstrap-light", "dark": "bootstrap-light"}
FONT_FAMILY = FONT
BASE_SIZE = BASE

KIND_GLYPH = {"folder": "▣", "project": "◆"}
STATUS_GLYPH = {
    "inbox": "○", "todo": "○", "in_progress": "◐", "waiting": "⏸", "testing": "◑", "done": "✓", "cancelled": "✕",
}


def dpi_scale(widget: tk.Misc) -> float:
    try:
        return float(widget.tk.call("tk", "scaling")) / (96 / 72)
    except tk.TclError:
        return 1.0


def apply_theme(root: tk.Misc, mode: str = "light") -> None:
    install(root)
    apply_input_colors(root)


def _walk(widget: tk.Misc):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def apply_input_colors(root: tk.Misc) -> None:
    """Culorile campurilor de text ale temei pentru widgeturile Tk clasice (tk.Text) si fundalul gol al listelor."""
    style = ttk.Style()
    dark = is_dark(root)
    bg = style.lookup("TEntry", "fieldbackground") or ("#212529" if dark else "#ffffff")
    fg = style.lookup("TEntry", "foreground") or ("#e9ecef" if dark else "#212529")
    style.configure("Treeview", fieldbackground=bg)
    try:
        accent = tb.Style().colors.primary
    except Exception:
        accent = "#0d6efd"
    # Selectia ramane colorata si cand lista nu are focusul (altfel devine aproape invizibila).
    style.map("Treeview", background=[("selected", C.selected)], foreground=[("selected", C.text)])
    root.option_add("*Text.background", bg)
    root.option_add("*Text.foreground", fg)
    root.option_add("*Text.insertBackground", fg)
    root.option_add("*Listbox.background", bg)
    root.option_add("*Listbox.foreground", fg)
    root.option_add("*Text.highlightBackground", C.border)
    root.option_add("*Text.highlightColor", C.accent)
    for w in _walk(root):
        if isinstance(w, tk.Text):
            w.configure(background=bg, foreground=fg, insertbackground=fg, borderwidth=0, relief="flat",
                        highlightthickness=1, highlightbackground=C.border, highlightcolor=C.accent)
        elif isinstance(w, tk.Listbox):
            w.configure(background=bg, foreground=fg)


def apply_fonts(root: tk.Misc) -> None:
    install(root)


def is_dark(root: tk.Misc) -> bool:
    return False


def muted_color(root: tk.Misc) -> str:
    return C.muted


def error_color(root: tk.Misc) -> str:
    return C.danger


def ok_color(root: tk.Misc) -> str:
    return C.success


def show_error(parent: tk.Misc, message: str, title: str = "Eroare") -> None:
    messagebox.showerror(title, message, parent=parent)


def show_info(parent: tk.Misc, message: str, title: str = "FocusDesk") -> None:
    messagebox.showinfo(title, message, parent=parent)


def confirm(parent: tk.Misc, message: str, title: str = "Confirmare") -> bool:
    return messagebox.askyesno(title, message, parent=parent)


def ask_choice(parent: tk.Misc, title: str, message: str, choices: list[tuple[str, str]]) -> str | None:
    """Dialog modal cu butoane personalizate; intoarce valoarea aleasa sau None la inchidere."""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)
    result: dict[str, str | None] = {"v": None}
    ttk.Label(dlg, text=message, wraplength=460, justify="left").pack(padx=16, pady=(16, 8))
    row = ttk.Frame(dlg)
    row.pack(padx=16, pady=(0, 14), anchor="e")

    def pick(v: str) -> None:
        result["v"] = v
        dlg.destroy()

    for value, label in choices:
        ttk.Button(row, text=label, command=lambda v=value: pick(v)).pack(side="left", padx=4)
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    center_on_parent(dlg, parent)
    dlg.grab_set()
    dlg.wait_window()
    return result["v"]


def center_on_parent(dlg: tk.Toplevel, parent: tk.Misc) -> None:
    dlg.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - dlg.winfo_reqwidth()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - dlg.winfo_reqheight()) // 3
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")


class ModalDialog(tk.Toplevel):
    """Baza pentru dialoguri modale: Enter = OK (daca `enter_confirms`), Escape = Anuleaza."""

    enter_confirms = True

    def __init__(self, parent: tk.Misc, title: str, *, resizable: bool = False, ok_text: str = "OK",
                 cancel_text: str = "Anulează") -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(resizable, resizable)
        self.result = None
        self.body = ttk.Frame(self, padding=(16, 14, 16, 6))
        self.body.pack(fill="both", expand=True)
        self.buttons = ttk.Frame(self, padding=(16, 6, 16, 14))
        self.buttons.pack(side="bottom", fill="x")
        self.ok_btn = tb.Button(self.buttons, text=ok_text, command=self._on_ok, bootstyle="primary")
        self.cancel_btn = ttk.Button(self.buttons, text=cancel_text, command=self.destroy)
        self.ok_btn.pack(side="right")
        self.cancel_btn.pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._parent = parent

    def _on_ok(self) -> None:
        if self.validate():
            res = self.collect()
            if res is False:
                return
            self.result = res
            self.destroy()

    def validate(self) -> bool:
        return True

    def collect(self):
        return None

    def run(self):
        if self.enter_confirms:
            self.bind("<Return>", lambda e: None if isinstance(e.widget, tk.Text) else self._on_ok())
        center_on_parent(self, self._parent)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()
        self.wait_window()
        return self.result


class ScrollFrame(ttk.Frame):
    """Cadru derulabil vertical (Canvas + Scrollbar); continutul se pune in `.inner`."""

    def __init__(self, parent: tk.Misc, **kw) -> None:
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)
        self.sync_background()

    def sync_background(self) -> None:
        bg = ttk.Style().lookup("TFrame", "background") or self.winfo_toplevel().cget("background")
        self.canvas.configure(background=bg)

    def _bind_wheel(self, _e=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _e=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e: tk.Event) -> None:
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


def make_tree(parent: tk.Misc, columns: list[tuple[str, str, int]], *, show_tree: bool = False,
              height: int = 8, selectmode: str = "browse") -> tuple[ttk.Treeview, ttk.Frame]:
    """Treeview cu bara de derulare; `columns` = (id, titlu, latime)."""
    frame = ttk.Frame(parent)
    ids = [c[0] for c in columns]
    tv = ttk.Treeview(frame, columns=ids, show=("tree headings" if show_tree else "headings"),
                      height=height, selectmode=selectmode)
    for cid, text, width in columns:
        tv.heading(cid, text=text, anchor="w")
        tv.column(cid, width=width, minwidth=40, anchor="w", stretch=(cid == ids[0] and not show_tree))
    vbar = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=vbar.set)
    hbar=ttk.Scrollbar(frame,orient="horizontal",command=tv.xview)
    tv.configure(xscrollcommand=hbar.set)
    frame.columnconfigure(0,weight=1)
    frame.rowconfigure(0,weight=1)
    tv.grid(row=0,column=0,sticky="nsew")
    vbar.grid(row=0,column=1,sticky="ns")
    hbar.grid(row=1,column=0,sticky="ew")
    return tv, frame


class Tooltip:
    def __init__(self, widget: tk.Misc, text: str) -> None:
        self.widget, self.text, self.tip = widget, text, None
        widget._focusdesk_tooltip = self
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None) -> None:
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, background=C.surface, foreground=C.text, relief="flat", borderwidth=0,
                 highlightthickness=1, highlightbackground=C.border,
                 padx=6, pady=3, wraplength=360, justify="left").pack()

    def _hide(self, _e=None) -> None:
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SessionButton(tb.Button):
    """Porneste sesiunea task-ului dat; cat timp o sesiune e activa devine „Oprește sesiunea”."""

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", node_getter: Callable[[], str | None]) -> None:
        super().__init__(parent, text="Începe sesiune", image=icon(parent,"play-on-accent"), compound="left", command=self._click, bootstyle="primary")
        self.app = app
        self._node_getter = node_getter
        self._mode = "start"
        app.session_buttons.append(self)

    def _click(self) -> None:
        if self._mode in ("pause","continue"):
            self.app.toggle_pause()
            return
        nid = self._node_getter()
        if nid:
            self.app.start_session(nid)

    def update_state(self) -> None:
        app = self.app
        ws = app.ws
        if ws is None:
            return
        nid = self._node_getter()
        if app.timer_active():
            same = app.timer.node_id == nid
            mode = ("pause" if app.timer.running else "continue") if same else "start"
            text = ("Pauză" if app.timer.running else "Continuă") if same else "Începe"
            node=ws.nodes.get(nid) if nid else None
            enabled = bool(node and node.kind==Kind.TASK and node.status not in CLOSED_STATUSES and not ws.read_only
                           and not app.timer.recovered and not app.timer.state.finalization)
        else:
            mode = "start"
            text = "Începe"
            node = ws.nodes.get(nid) if nid else None
            enabled = (node is not None and node.kind == Kind.TASK and node.status not in CLOSED_STATUSES
                       and not ws.read_only)
        if mode != self._mode:
            self.configure(bootstyle="danger-outline" if mode == "pause" else "primary")
            self.configure(image=icon(self,"pause" if mode=="pause" else "play-on-accent"))
            self._mode = mode
        if str(self.cget("text")) != text:
            self.configure(text=text)
        self.configure(state="normal" if enabled else "disabled")


class _AskString(ModalDialog):
    def __init__(self, parent: tk.Misc, title: str, prompt: str, initial: str, ok_text: str) -> None:
        super().__init__(parent, title, ok_text=ok_text)
        ttk.Label(self.body, text=prompt).pack(anchor="w")
        self.var = tk.StringVar(value=initial)
        self.entry = ttk.Entry(self.body, textvariable=self.var, width=54)
        self.entry.pack(fill="x", pady=6)
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def validate(self) -> bool:
        return bool(self.var.get().strip())

    def collect(self) -> str:
        return self.var.get().strip()


def ask_string(parent: tk.Misc, title: str, prompt: str, initial: str = "", ok_text: str = "OK") -> str | None:
    return _AskString(parent, title, prompt, initial, ok_text).run()
