"""Pagina „Astăzi”: priorități, sesiuni planificate, întârzieri."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from ..domain.labels import PRIORITY_LABELS, STATUS_LABELS, format_minutes
from ..domain.models import CLOSED_STATUSES, Kind, Node
from .common import ScrollFrame, error_color, muted_color
from .dialogs import NodePickerDialog
from .design import C, button, icon
from .formats import format_date

if TYPE_CHECKING:
    from .app import FocusDeskApp

_DAYS = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]
_MONTHS = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie",
           "octombrie", "noiembrie", "decembrie"]


def long_date(d: date) -> str:
    return f"{_DAYS[d.weekday()].capitalize()}, {d.day} {_MONTHS[d.month - 1]} {d.year}"


class TodayPage(ttk.Frame):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent)
        self.app = app
        self.sf = ScrollFrame(self)
        self.sf.pack(fill="both", expand=True)
        self.sf.inner.configure(style="Page.TFrame")
        self.sf.canvas.configure(background=C.canvas)

    def refresh(self) -> None:
        self.sf.canvas.configure(background=C.canvas)
        for w in self.sf.inner.winfo_children():
            w.destroy()
        app, ws, q = self.app, self.app.ws, self.app.q
        f = self.sf.inner
        f.columnconfigure(0, weight=1)
        today = q.today()
        head = ttk.Frame(f, style="Page.TFrame")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ttk.Label(head, text="Astăzi", style="Page.Title.TLabel").pack(side="left")
        ttk.Label(f, text=long_date(today), style="Page.Muted.TLabel").grid(row=1, column=0, sticky="w", padx=18, pady=(0,8))
        resume = button(head, "Reia lucrul", app.resume_work, kind="Primary", glyph="play")
        resume.pack(side="right")
        last = app.last_worked_node()
        if last is None and not app.timer_active():
            resume.state(["disabled"])
        if ws.read_only:
            resume.state(["disabled"])
        summary = ttk.Frame(f, style="Page.TFrame")
        summary.grid(row=3,column=0,sticky="ew",padx=16,pady=(10,0))
        summary.columnconfigure((0,1,2),weight=1,uniform="metric")
        for index,(value,label) in enumerate(((len(q.pinned_today()),"Priorități"),(len(q.sessions_on(today)),"Sesiuni azi"),(len(q.view_overdue()),"Restante"))):
            tile=ttk.Frame(summary,style="Card.TFrame",padding=(12,10))
            tile.grid(row=0,column=index,sticky="ew",padx=(0,6) if index<2 else 0)
            ttk.Label(tile,text=str(value),style="Metric.TLabel").pack(anchor="w")
            ttk.Label(tile,text=label,style="Muted.TLabel").pack(anchor="w")
        self.timer_label = ttk.Label(f,text="",style="Page.Muted.TLabel",wraplength=500)
        self.timer_label.grid(row=4,column=0,sticky="ew",padx=18,pady=(8,0))
        self.update_timer()
        row = 5

        def section(title: str, hint: str = "") -> ttk.Frame:
            nonlocal row
            box = ttk.Frame(f, style="Card.TFrame", padding=(14,12))
            box.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 2))
            box.columnconfigure(0, weight=1)
            hdr = ttk.Frame(box)
            hdr.grid(row=0, column=0, sticky="ew")
            ttk.Label(hdr, text=title, style="Section.TLabel").pack(side="left")
            if hint:
                ttk.Label(box, text=hint, style="Muted.TLabel").grid(row=1,column=0,sticky="w",pady=(2,8))
            if not hint:
                ttk.Frame(box, height=6).grid(row=1, column=0, sticky="ew")
            row += 1
            return box

        # Prioritati
        pinned = q.pinned_today()
        box = section(f"Priorități ({len(pinned)}/{ws.settings.max_today_priorities})",
                      "alese de tine pentru azi")
        r = 2
        for n in pinned:
            self._task_row(box, r, n, unpin=True)
            r += 1
        if not pinned:
            ttk.Label(box, text="Nicio prioritate aleasă. Poți marca până la "
                      f"{ws.settings.max_today_priorities} task-uri.", style="Muted.TLabel").grid(
                row=r, column=0, sticky="w")
            r += 1
        add = ttk.Button(box, text="+ Alege prioritate…", command=self._pick_priority)
        add.grid(row=r, column=0, sticky="w", pady=(6, 0))
        if len(pinned) >= ws.settings.max_today_priorities or ws.read_only:
            add.state(["disabled"])

        # Sesiuni planificate
        sessions = q.sessions_on(today)
        box = section("Sesiuni planificate azi")
        if not sessions:
            ttk.Label(box, text="Nicio sesiune planificată.", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        for i, s in enumerate(sessions):
            node = ws.nodes.get(s.node_id)
            if node is None:
                continue
            tz = q.tz()
            fr = ttk.Frame(box)
            fr.grid(row=2 + i, column=0, sticky="ew", pady=1)
            when = f"{s.start_at.astimezone(tz):%H:%M}–{s.end_at.astimezone(tz):%H:%M}"
            ttk.Label(fr, text=when, width=13).pack(side="left")
            link = ttk.Label(fr, text=node.title, cursor="hand2", style="Link.TLabel")
            link.pack(side="left")
            link.bind("<Button-1>", lambda _e, nid=node.id: app.select_node(nid, reveal=True))
            if s.status == "planned" and not ws.read_only:
                ttk.Button(fr, text="Începe", command=lambda nid=node.id, sid=s.id: app.start_session(nid, sid)
                           ).pack(side="right")

        # Intarzieri
        overdue = q.view_overdue()
        box = section(f"Întârzieri ({len(overdue)})", "termene depășite")
        for i, n in enumerate(overdue[:8]):
            self._task_row(box, 2 + i, n)
        if not overdue:
            ttk.Label(box, text="Nicio întârziere.", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        elif len(overdue) > 8:
            more = ttk.Label(box, text=f"… încă {len(overdue) - 8} în vizualizarea „Restante”", style="Link.TLabel",
                             cursor="hand2")
            more.grid(row=10, column=0, sticky="w")
            more.bind("<Button-1>", lambda _e: app.show_view("overdue", select_sidebar=True))

        # Termen azi
        due_today = [n for n in q.view_today() if q.due_day(n) == today and n.id not in {p.id for p in pinned}]
        if due_today:
            box = section(f"Cu termen azi ({len(due_today)})")
            for i, n in enumerate(due_today[:10]):
                self._task_row(box, 2 + i, n)

    def _task_row(self, parent: tk.Misc, r: int, n: Node, unpin: bool = False) -> None:
        app, q = self.app, self.app.q
        fr = ttk.Frame(parent, style="Card.TFrame", padding=(8,8))
        fr.grid(row=r, column=0, sticky="ew", pady=4)
        fr.columnconfigure(0, weight=1)
        title = ttk.Label(fr, text=n.title, cursor="hand2", style="Link.TLabel", wraplength=360)
        title.grid(row=0, column=0, sticky="w")
        title.bind("<Button-1>", lambda _e: app.select_node(n.id, reveal=True))
        due = q.due_day(n)
        rem = n.remaining_minutes if n.remaining_minutes is not None else n.estimated_minutes
        bits = [STATUS_LABELS.get(n.status, "") if n.status else "", PRIORITY_LABELS.get(n.priority, "") if n.priority else "",
                f"termen {format_date(due)}" if due else "", f"rămas: {format_minutes(rem)}"]
        color = error_color(self) if q.is_overdue(n) else muted_color(self)
        meta = ttk.Label(fr, text="  ·  ".join(b for b in bits if b), style="Muted.TLabel", foreground=color, wraplength=420)
        meta.grid(row=1, column=0, columnspan=2, sticky="w",pady=(4,0))
        fr.bind("<Configure>",lambda e: (title.configure(wraplength=max(160,e.width-40)),meta.configure(wraplength=max(160,e.width-40))))
        if n.next_action:
            ttk.Label(fr, text=f"Următorul pas: {n.next_action}", style="Muted.TLabel", wraplength=360).grid(row=2, column=0, sticky="w")
        btns = ttk.Frame(fr)
        btns.grid(row=3, column=0, columnspan=2, sticky="w",pady=(6,0))
        if not app.ws.read_only:
            if n.status not in CLOSED_STATUSES:
                ttk.Button(btns, text="Începe sesiune", command=lambda: app.start_session(n.id)).pack(side="left", padx=2)
            if unpin:
                ttk.Button(btns, text="Scoate", command=lambda: app.set_pinned(n.id, False)).pack(side="left", padx=2)

    def update_timer(self):
        if not hasattr(self,"timer_label"):
            return
        timer = self.app.timer
        from ..domain.labels import format_seconds
        if timer and timer.state and timer.recovered is None:
            node=self.app.ws.nodes.get(timer.node_id)
            self.timer_label.configure(text=("În lucru" if timer.running else "Pauză") + " · " + (node.title if node else "Task") + " · " + format_seconds(timer.seconds))
        else:
            self.timer_label.configure(text="Nicio sesiune activă. Alege o prioritate pentru a începe.")

    def _pick_priority(self) -> None:
        ws = self.app.ws
        pinned = {n.id for n in self.app.q.pinned_today()}
        picked = NodePickerDialog(self, ws, "Alege prioritate pentru azi", exclude=pinned, only_tasks=True).run()
        if picked:
            self.app.set_pinned(picked, True)
