"""Tabul „Planificare” (sesiuni ale task-ului) si pagina Calendar (agenda)."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from ..domain.labels import SESSION_STATUS_LABELS, format_seconds
from ..domain.models import Kind, Node
from ..domain.session import SessionRecord
from ..domain.timeutil import local_day_bounds_utc, utc_to_local
from ..errors import FocusDeskError
from .common import ScrollFrame, confirm, error_color, make_tree, muted_color, show_error, show_info
from .formats import format_date
from .inspector import InspectorTab
from .outlook_ui import ConflictsDialog
from .planning import ManualSessionDialog, PlannerDialog, RecurrenceDialog, fmt_range, sync_state_text

if TYPE_CHECKING:
    from .app import FocusDeskApp


class PlanTab(InspectorTab):
    title = "Planificare"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, app)
        self._ids: dict[str, SessionRecord] = {}
        self.avail_lbl = ttk.Label(self, text="", style="Muted.TLabel", wraplength=400, justify="left")
        self.avail_lbl.pack(anchor="w", padx=8, pady=(8, 2))
        self.tv, frame = make_tree(self, [("when", "Interval", 140), ("status", "Status", 80), ("worked", "Lucrat", 60),
                                          ("cal", "Calendar", 170)], height=8)
        frame.pack(fill="both", expand=True, padx=8)
        self.tv.tag_configure("past", foreground=muted_color(self))
        self.tv.tag_configure("bad", foreground=error_color(self))
        r1 = ttk.Frame(self)
        r1.pack(fill="x", padx=8, pady=6)
        self.btns: list[ttk.Button] = []
        for text, cmd in (("Programează…", self._new), ("Modifică…", self._edit), ("Anulează", self._cancel),
                          ("Asistată…", self._assist)):
            b = ttk.Button(r1, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.btns.append(b)
        r2 = ttk.Frame(self)
        r2.pack(fill="x", padx=8)
        ttk.Button(r2, text="Exportă ICS (viitoare)…", command=self._export).pack(side="left", padx=2)
        self.extra_row = ttk.Frame(self)
        self.extra_row.pack(fill="x", padx=8, pady=(4, 0))
        self.detail = ttk.Label(self, text="", style="Muted.TLabel", wraplength=400, justify="left")
        self.detail.pack(anchor="w", padx=8, pady=8)
        self.tv.bind("<<TreeviewSelect>>", self._on_select)
        self._build_extra()

    def _build_extra(self) -> None:
        ttk.Button(self.extra_row, text="Sincronizează cu Outlook",
                   command=lambda: self.app.outlook.sync()).pack(side="left", padx=2)

    def applies_to(self, node: Node) -> bool:
        return node.kind == Kind.TASK

    def load(self, node: Node) -> None:
        super().load(node)
        tz = self.app.ws.settings.timezone
        selected, scroll, horizontal = self.tv.selection(), self.tv.yview()[0], self.tv.xview()[0]
        self.tv.delete(*self.tv.get_children())
        self._ids = {}
        for s in self.app.sessions.for_node(node.id):
            self._ids[s.id] = s
            tags = []
            if s.status in ("done", "cancelled", "missed"):
                tags.append("past")
            if s.sync.state in ("failed", "conflict"):
                tags.append("bad")
            self.tv.insert("", "end", iid=s.id, tags=tags, values=(
                fmt_range(s, tz), SESSION_STATUS_LABELS.get(s.status, s.status),
                format_seconds(s.actual_seconds) if s.actual_seconds else "—", sync_state_text(s)))
        self.tv.selection_set([i for i in selected if self.tv.exists(i)])
        self.tv.yview_moveto(scroll)
        self.tv.xview_moveto(horizontal)
        self.avail_lbl.configure(text=self.app.availability_hint())
        self.detail.configure(text="")
        ro = self.app.ws.read_only
        for b in self.btns:
            b.configure(state="disabled" if ro else "normal")

    def _on_select(self, _e=None) -> None:
        s = self._selected()
        if s is not None:
            self.detail.configure(text=sync_state_text(s) if s.sync.state != "none" else "")

    def _selected(self) -> SessionRecord | None:
        sel = self.tv.selection()
        return self._ids.get(sel[0]) if sel else None

    def _refresh(self) -> None:
        if self.node_id and self.node_id in self.app.ws.nodes:
            self.load(self.app.ws.get(self.node_id))
        self.app.on_sessions_changed()

    def _new(self) -> None:
        if ManualSessionDialog(self, self.app, self.node_id).run():
            self._refresh()

    def _edit(self) -> None:
        s = self._selected()
        if s is None:
            return
        if s.status != "planned":
            show_info(self, "Se pot modifica doar sesiunile planificate.")
            return
        if ManualSessionDialog(self, self.app, session=s).run():
            self._refresh()

    def _cancel(self) -> None:
        s = self._selected()
        if s is None or s.status not in ("planned", "active"):
            return
        if confirm(self, "Anulezi sesiunea? Dacă este în Outlook, anularea se va aplica la următoarea sincronizare."):
            if self.app.run_write(lambda: self.app.sessions.cancel(s.id)):
                self._refresh()

    def _assist(self) -> None:
        if self.node_id and PlannerDialog(self, self.app, [self.node_id]).run():
            self._refresh()

    def _export(self) -> None:
        if not self.node_id:
            return
        now = datetime.now().astimezone()
        sessions = [s for s in self.app.sessions.for_node(self.node_id)
                    if s.status in ("planned", "cancelled") and s.end_at > now]
        self.app.export_ics(sessions)
        self._refresh()


class CalendarPage(ttk.Frame):
    """Agenda: sesiunile din ultimele zile si urmatoarele N zile, grupate pe zile."""

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent)
        self.app = app
        self._ids: dict[str, SessionRecord] = {}
        self._outlook_events = []
        self._outlook_key = None
        self._outlook_loading_key = None
        self._outlook_error = ""
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 2))
        ttk.Label(top, text="Calendar", style="Title.TLabel").pack(side="left")
        self.days_var = tk.StringVar(value="14 zile")
        box = ttk.Combobox(top, textvariable=self.days_var, values=["7 zile", "14 zile", "30 zile"], state="readonly",
                           width=9)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(top, text="Orizont:").pack(side="right", padx=4)
        self.hint = ttk.Label(self, text="", style="Muted.TLabel", wraplength=900, justify="left")
        self.hint.pack(fill="x", padx=12)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=6)
        self.action_btns: list[ttk.Button] = []
        for text, cmd in (("Programare manuală…", self._manual), ("Planificare asistată…", self._assist),
                          ("Modifică…", self._edit), ("Anulează sesiunea", self._cancel),
                          ("Exportă ICS…", self._export), ("Task-uri recurente…", self._recurrence)):
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.action_btns.append(b)
        self.extra_bar = ttk.Frame(self)
        self.extra_bar.pack(fill="x",padx=12)
        self._build_extra()
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.tv = ttk.Treeview(wrap, columns=("time", "task", "status", "cal"), show="tree headings",
                               selectmode="browse")
        self.tv.heading("#0", text="Zi", anchor="w")
        self.tv.heading("time", text="Interval", anchor="w")
        self.tv.heading("task", text="Task", anchor="w")
        self.tv.heading("status", text="Status", anchor="w")
        self.tv.heading("cal", text="Calendar", anchor="w")
        self.tv.column("#0", width=170, stretch=False)
        self.tv.column("time", width=110, stretch=False)
        self.tv.column("task", width=330)
        self.tv.column("status", width=90, stretch=False)
        self.tv.column("cal", width=260)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.hbar=ttk.Scrollbar(wrap,orient="horizontal",command=self.tv.xview)
        self.tv.configure(xscrollcommand=self.hbar.set)
        wrap.rowconfigure(0,weight=1)
        wrap.columnconfigure(0,weight=1)
        self.tv.grid(row=0,column=0,sticky="nsew")
        sb.grid(row=0,column=1,sticky="ns")
        self.hbar.grid(row=1,column=0,sticky="ew")
        self.tv.tag_configure("day", font=(self._root()._focusdesk_family, 10, "bold"))
        self.tv.tag_configure("past", foreground=muted_color(self))
        self.tv.tag_configure("bad", foreground=error_color(self))
        self.tv.bind("<Double-1>", self._open_task)

    def _build_extra(self) -> None:
        """Butoane de integrare Outlook."""
        for text, cmd in (("Reîncarcă Outlook", lambda: self.refresh(force_outlook=True)),
                          ("Testează Outlook…", lambda: self.app.outlook.test()),
                          ("Sincronizează cu Outlook", lambda: self._sync()),
                          ("Conflicte…", lambda: self._conflicts())):
            ttk.Button(self.extra_bar, text=text, command=cmd).pack(side="left", padx=2)

    def _sync(self) -> None:
        self.app.outlook.sync()

    def _conflicts(self) -> None:
        n = len(self.app.outlook.conflicts())
        if not n:
            show_info(self, "Nu există conflicte cu Outlook.")
            return
        ConflictsDialog(self, self.app).run()
        self.refresh()

    def horizon(self) -> int:
        return int(self.days_var.get().split()[0])

    def refresh(self, *, force_outlook: bool = False) -> None:
        app = self.app
        tz = app.ws.settings.timezone
        today = app.q.today()
        first = today - timedelta(days=3)
        last = today + timedelta(days=self.horizon())
        start = local_day_bounds_utc(first, tz)[0]
        end = local_day_bounds_utc(last, tz)[1]
        outlook_key = (first, last, app.outlook.settings.calendar_store_id,
                       app.outlook.settings.calendar_folder_id)
        if not app.outlook.enabled():
            self._outlook_events, self._outlook_key, self._outlook_error = [], None, ""
        elif force_outlook or (self._outlook_key != outlook_key and self._outlook_loading_key != outlook_key):
            self._outlook_loading_key = outlook_key

            def loaded(events) -> None:
                if self._outlook_loading_key != outlook_key:
                    return
                self._outlook_loading_key = None
                self._outlook_key, self._outlook_events, self._outlook_error = outlook_key, events, ""
                self.refresh()

            def failed(exc: BaseException) -> None:
                if self._outlook_loading_key != outlook_key:
                    return
                self._outlook_loading_key = None
                self._outlook_key, self._outlook_events = outlook_key, []
                self._outlook_error = f"Nu s-au putut citi ședințele Outlook: {exc}"
                self.refresh()

            app.outlook.get_calendar_events(first, last, loaded, failed)
        sessions = app.sessions.between(start, end, ("planned", "active", "done", "missed", "cancelled"))
        by_day: dict[date, list[SessionRecord]] = {}
        for s in sessions:
            by_day.setdefault(utc_to_local(s.start_at, tz).date(), []).append(s)
        own_session_ids = {s.id for s in app.sessions.all()}
        outlook_by_day = {}
        for event in self._outlook_events if self._outlook_key == outlook_key else []:
            if event.session_id in own_session_ids:
                continue
            outlook_by_day.setdefault(utc_to_local(event.start, tz).date(), []).append(event)
        selected, scroll, horizontal = self.tv.selection(), self.tv.yview()[0], self.tv.xview()[0]
        self.tv.delete(*self.tv.get_children())
        self._ids = {}
        from .today import long_date

        d = first
        while d <= last:
            items = by_day.get(d, [])
            outlook_items = outlook_by_day.get(d, [])
            work = app.ws.settings.work_hours.get(str(d.weekday()))
            working = bool(work and work.enabled and d not in app.ws.settings.holidays)
            if items or outlook_items or d == today:
                label = long_date(d) + ("  (azi)" if d == today else "")
                if not working:
                    label += "  · nelucrătoare"
                node = self.tv.insert("", "end", iid=f"day:{d.isoformat()}", text=label, open=True, tags=("day",))
                agenda = [(s.start_at, "session", s) for s in items]
                agenda += [(event.start, "outlook", event) for event in outlook_items]
                for index, (_start, kind, item) in enumerate(sorted(agenda, key=lambda row: row[0])):
                    if kind == "session":
                        s = item
                        n = app.ws.nodes.get(s.node_id)
                        tags = []
                        if s.status in ("done", "cancelled", "missed"):
                            tags.append("past")
                        if s.sync.state in ("failed", "conflict"):
                            tags.append("bad")
                        self._ids[s.id] = s
                        a, b = utc_to_local(s.start_at, tz), utc_to_local(s.end_at, tz)
                        self.tv.insert(node, "end", iid=s.id, tags=tags, values=(
                            f"{a:%H:%M}–{b:%H:%M}", n.title if n else "?",
                            SESSION_STATUS_LABELS.get(s.status, s.status), sync_state_text(s)))
                    else:
                        event = item
                        a, b = utc_to_local(event.start, tz), utc_to_local(event.end, tz)
                        interval = "Toată ziua" if event.all_day else f"{a:%H:%M}–{b:%H:%M}"
                        self.tv.insert(node, "end", iid=f"outlook:{d.isoformat()}:{index}",
                                       values=(interval, event.subject or "Ședință Outlook", "Outlook", "Outlook"))
                if not items and not outlook_items:
                    self.tv.insert(node, "end", values=("", "Nicio sesiune", "", ""))
            d += timedelta(days=1)
        self.tv.selection_set([i for i in selected if self.tv.exists(i)])
        self.tv.yview_moveto(scroll)
        self.tv.xview_moveto(horizontal)
        hint = app.availability_hint() + "  Timpul planificat nu este timp lucrat."
        if self._outlook_error:
            hint += "  " + self._outlook_error
        self.hint.configure(text=hint)
        ro = app.ws.read_only
        for b in self.action_btns:
            b.configure(state="disabled" if ro else "normal")

    def _selected(self) -> SessionRecord | None:
        sel = self.tv.selection()
        return self._ids.get(sel[0]) if sel else None

    def _changed(self) -> None:
        self.refresh()
        self.app.on_sessions_changed()

    def _manual(self) -> None:
        if ManualSessionDialog(self, self.app).run():
            self._changed()

    def _assist(self) -> None:
        if PlannerDialog(self, self.app).run():
            self._changed()

    def _edit(self) -> None:
        s = self._selected()
        if s is None or s.status != "planned":
            show_info(self, "Selectează o sesiune planificată.")
            return
        if ManualSessionDialog(self, self.app, session=s).run():
            self._changed()

    def _cancel(self) -> None:
        s = self._selected()
        if s is None or s.status not in ("planned", "active"):
            show_info(self, "Selectează o sesiune planificată.")
            return
        if confirm(self, "Anulezi sesiunea selectată?"):
            if self.app.run_write(lambda: self.app.sessions.cancel(s.id)):
                self._changed()

    def _export(self) -> None:
        now = datetime.now().astimezone()
        sessions = [s for s in self.app.sessions.all() if s.status in ("planned",) and s.end_at > now]
        sessions += [s for s in self.app.sessions.all() if s.status == "cancelled" and s.sync.state == "exported"]
        self.app.export_ics(sessions)
        self.refresh()

    def _recurrence(self) -> None:
        RecurrenceDialog(self, self.app).run()
        self.app.refresh_all()

    def _open_task(self, _e=None) -> None:
        s = self._selected()
        if s is not None:
            self.app.select_node(s.node_id, reveal=True)
