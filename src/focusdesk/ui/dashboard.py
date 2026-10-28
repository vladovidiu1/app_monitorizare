"""Fereastra Dashboard: calendar lunar cu timpul lucrat pe zile si pe task-uri."""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from ..domain.labels import format_worked
from .common import muted_color, ok_color
from .design import C
from ..services.activity import activity_model, ActivityFilters, live_snapshot
from .tree_rows import sync_rows

if TYPE_CHECKING:
    from .app import FocusDeskApp

MONTHS = ["Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie", "Iulie", "August", "Septembrie",
          "Octombrie", "Noiembrie", "Decembrie"]
WEEKDAYS = ["Lun", "Mar", "Mie", "Joi", "Vin", "Sâm", "Dum"]


def _short(seconds: int) -> str:
    if seconds < 60:
        return "< 1m"
    h, m = divmod(round(seconds / 60), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


class DashboardWindow(tk.Toplevel):
    def __init__(self, app: "FocusDeskApp") -> None:
        super().__init__(app.root)
        self.app = app
        self.title("Activitate — calendar lunar")
        self.project_id = app.activity_page._project_options.get(app.activity_page.project.get(), "*")
        self.focus_projects = app.activity_page._focus_projects
        self._focus_day = None
        self.geometry("1080x660")
        self.minsize(820, 520)
        today = app.q.today()
        self.year, self.month = today.year, today.month
        self.selected: date | None = None
        self._data: dict[date, dict[str, int]] = {}

        top = ttk.Frame(self, padding=(14, 12, 14, 4))
        top.pack(fill="x")
        ttk.Button(top, text="◀", width=3, command=lambda: self._shift(-1)).pack(side="left")
        self.month_lbl = ttk.Label(top, text="", style="Title.TLabel", width=20, anchor="center")
        self.month_lbl.pack(side="left", padx=6)
        ttk.Button(top, text="▶", width=3, command=lambda: self._shift(1)).pack(side="left")
        tb.Button(top, text="Luna curentă", command=self._go_today, bootstyle="secondary-outline"
                  ).pack(side="left", padx=(12, 0))
        self.summary_lbl = ttk.Label(top, text="", style="Muted.TLabel")
        self.summary_lbl.pack(side="right")

        body = ttk.Frame(self, padding=(14, 6, 14, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        self.grid_frame = ttk.Frame(body)
        self.grid_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        side = ttk.Frame(body)
        side.grid(row=0, column=1, sticky="nsew")
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)
        head = ttk.Frame(side)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.side_lbl = ttk.Label(head, text="", style="Section.TLabel")
        self.side_lbl.pack(side="left")
        self.month_btn = ttk.Button(head, text="Toată luna", command=lambda: self._select(None))
        self.month_btn.pack(side="right")
        self.tv = ttk.Treeview(side, columns=("task", "where", "time"), show="headings", selectmode="browse")
        self.tv.heading("task", text="Task", anchor="w")
        self.tv.heading("where", text="Locație", anchor="w")
        self.tv.heading("time", text="Lucrat", anchor="w")
        self.tv.column("task", width=170)
        self.tv.column("where", width=120)
        self.tv.column("time", width=80, stretch=False)
        vbar = ttk.Scrollbar(side, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=vbar.set)
        self.tv.grid(row=1, column=0, sticky="nsew")
        vbar.grid(row=1, column=1, sticky="ns")
        self.tv.bind("<Double-1>", self._open_task)
        self.tv.bind("<Return>", self._open_task)
        self.total_lbl = ttk.Label(side, text="", style="Muted.TLabel")
        self.total_lbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(side, text="Dublu-clic pe un task îl deschide în aplicație. Contează doar sesiunile pornite din "
                  "actual_seconds; timpul live este separat, fără dublare.", style="Muted.TLabel", wraplength=380, justify="left"
                  ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()

    # ---- navigation -----------------------------------------------------
    def _shift(self, delta: int) -> None:
        m = self.month - 1 + delta
        self.year += m // 12
        self.month = m % 12 + 1
        self.selected = None
        self.refresh()

    def _go_today(self) -> None:
        today = self.app.q.today()
        self.year, self.month, self.selected = today.year, today.month, None
        self.refresh()

    def _select(self, day: date | None) -> None:
        self.selected = None if day == self.selected else day
        self.refresh()

    # ---- drawing --------------------------------------------------------
    def _rgb(self, color: str) -> tuple[int, int, int]:
        r, g, b = self.winfo_rgb(color)
        return r >> 8, g >> 8, b >> 8

    def _blend(self, base: str, accent: str, t: float) -> tuple[str, str]:
        """Culoare de fundal amestecata + culoare de text lizibila pe ea."""
        a, b = self._rgb(base), self._rgb(accent)
        rgb = tuple(round(x + (y - x) * t) for x, y in zip(a, b))
        lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return "#%02x%02x%02x" % rgb, ("#111111" if lum > 0.55 else "#f5f5f5")

    def refresh(self) -> None:
        if self.app.ws is None:
            self.destroy()
            return
        app = self.app
        first = date(self.year, self.month, 1)
        last = date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])
        self.report = activity_model(app.ws).report(ActivityFilters(first,last,self.project_id,focus_projects=self.focus_projects),live=live_snapshot(app))
        self._data = self.report.saved_by_day()
        self.month_lbl.configure(text=f"{MONTHS[self.month - 1]} {self.year}")
        self._draw_grid(first, last)
        self._fill_list()
        total = sum(sum(d.values()) for d in self._data.values())
        tasks = {n for d in self._data.values() for n in d}
        self.summary_lbl.configure(
            text=f"Salvat: {format_worked(total) or '0 min'} · Live separat: {format_worked(self.report.live) or '0 min'}")

    def _draw_grid(self, first: date, last: date) -> None:
        for w in self.grid_frame.winfo_children():
            w.destroy()
        style = ttk.Style()
        base = style.lookup("TFrame", "background") or self.cget("background")
        fg = style.lookup("TLabel", "foreground") or "#000000"
        accent = C.accent
        muted = muted_color(self)
        today = self.app.q.today()
        weeks = calendar.Calendar(0).monthdatescalendar(self.year, self.month)
        peak = max((sum(d.values()) for d in self._data.values()), default=0)
        gf = self.grid_frame
        for c in range(7):
            gf.columnconfigure(c, weight=1, uniform="day")
            ttk.Label(gf, text=WEEKDAYS[c], style="Muted.TLabel", anchor="center").grid(row=0, column=c, pady=(0, 4))
        for r, week in enumerate(weeks, start=1):
            gf.rowconfigure(r, weight=1, uniform="week")
            for c, day in enumerate(week):
                in_month = first <= day <= last
                secs = sum(self._data.get(day, {}).values()) if in_month else 0
                bg, text_fg = base, (fg if in_month else muted)
                if secs:
                    bg, text_fg = self._blend(base, accent, 0.2 + 0.6 * secs / peak)
                border = accent if day == self.selected else (muted if day == today else C.border)
                cell = tk.Frame(gf, background=bg, highlightthickness=2 if border != base else 1,
                                highlightbackground=border, highlightcolor=border)
                cell.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
                tk.Label(cell, text=str(day.day), background=bg, foreground=text_fg, anchor="nw",
                         font=(self._root()._focusdesk_family, 9, "bold" if day == today else "normal")).pack(anchor="nw", padx=4)
                if secs:
                    tk.Label(cell, text=_short(secs), background=bg, foreground=text_fg,
                             font=(self._root()._focusdesk_family, 11, "bold")).pack(expand=True)
                    n = len(self._data[day])
                    tk.Label(cell, text=f"{n} task-uri" if n != 1 else "1 task", background=bg, foreground=text_fg,
                             font=(self._root()._focusdesk_family, 8)).pack(side="bottom", pady=(0, 3))
                if in_month:
                    cell.configure(takefocus=True)
                    for w in (cell, *cell.winfo_children()):
                        w.bind("<Button-1>", lambda _e, d=day: self._select(d))
                    def focus_in(event,d=day,w=cell):
                        self._focus_day=d;w.configure(highlightbackground=C.accent,highlightcolor=C.accent)
                    cell.bind('<FocusIn>',focus_in)
                    cell.bind('<FocusOut>',lambda event,w=cell,border=border:w.configure(highlightbackground=border))
                    if day==self._focus_day:cell.focus_set()
                    cell.bind('<Return>',lambda event,d=day:self._select(d))
                    cell.bind('<space>',lambda event,d=day:self._select(d))

    def _fill_list(self) -> None:
        ws = self.app.ws
        if self.selected is not None:
            rows = dict(self._data.get(self.selected, {}))
            self.side_lbl.configure(text=f"{self.selected:%d.%m.%Y}")
            self.month_btn.state(["!disabled"])
        else:
            rows = {}
            for d in self._data.values():
                for nid, s in d.items():
                    rows[nid] = rows.get(nid, 0) + s
            self.side_lbl.configure(text=f"{MONTHS[self.month - 1]} — toată luna")
            self.month_btn.state(["disabled"])
        rendered = []
        for nid, secs in sorted(rows.items(), key=lambda kv: kv[1], reverse=True):
            node = ws.nodes.get(nid)
            where = " › ".join(a.title for a in ws.ancestors(nid)) if node else ''
            rendered.append(('',nid,dict(values=(node.title if node else 'Task indisponibil',where,format_worked(secs)))))
        sync_rows(self.tv,rendered)
        total = sum(rows.values())
        self.total_lbl.configure(text=f"Total: {format_worked(total) or '0 min'}" if rows else "Nicio sesiune lucrată.")

    def _open_task(self, _event=None) -> None:
        sel = self.tv.selection()
        if sel and sel[0] in self.app.ws.nodes:
            self.app.root.deiconify()
            self.app.select_node(sel[0], reveal=True)
            self.app.root.lift()
