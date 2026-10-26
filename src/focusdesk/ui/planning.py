"""Dialoguri de planificare: programare manuala, planificare asistata, recurente."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, time, timedelta
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from ..domain.labels import PRIORITY_LABELS, SESSION_STATUS_LABELS, format_minutes
from ..domain.models import CLOSED_STATUSES, Kind, Node, Priority
from ..domain.session import SessionRecord
from ..domain.timeutil import AmbiguousLocalTime, local_to_utc, utc_to_local
from ..errors import FocusDeskError
from ..integrations.ics import EXPORT_STATE_TEXT
from ..services.planner import PlanRequest, ProposedSession
from ..services.sessions import BlockedByDependencies, OverlapError, session_signature
from .common import ModalDialog, ask_choice, confirm, make_tree, show_error, show_info, muted_color
from .dialogs import NodePickerDialog, location_choices
from .formats import duration_to_text, format_date, parse_date, parse_duration, parse_tags, parse_time

if TYPE_CHECKING:
    from .app import FocusDeskApp

WEEKDAYS = ["Lu", "Ma", "Mi", "Jo", "Vi", "Sâ", "Du"]


def sync_state_text(s: SessionRecord) -> str:
    st = s.sync.state
    if st == "none":
        return "—"
    if st == "exported":
        text = EXPORT_STATE_TEXT
        if s.sync.signature and s.sync.signature != session_signature(s):
            text += " (modificat după export)"
        return text
    return {
        "pending": "În așteptare (nesincronizat)",
        "saved_locally": "Salvat în Outlook local (sincronizarea Exchange neconfirmată)",
        "failed": "Eșuat" + (f": {s.sync.error}" if s.sync.error else ""),
        "conflict": "Conflict cu Outlook",
        "detached": "Detașat de calendar",
        "cancelled": "Anulat",
    }.get(st, st)


def fmt_range(s: SessionRecord, tz: str) -> str:
    a, b = utc_to_local(s.start_at, tz), utc_to_local(s.end_at, tz)
    return f"{a:%d.%m.%Y %H:%M}–{b:%H:%M}"


class ManualSessionDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", node_id: str | None = None,
                 session: SessionRecord | None = None) -> None:
        super().__init__(parent, "Modifică sesiunea" if session else "Programează sesiune",
                         ok_text="Salvează" if session else "Programează")
        self.app = app
        self.session = session
        tz = app.ws.settings.timezone
        self.node_id = session.node_id if session else node_id
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text="Task").grid(row=0, column=0, sticky="w", pady=4)
        self.task_lbl = ttk.Label(b, text="(alege un task)", width=42)
        self.task_lbl.grid(row=0, column=1, sticky="w")
        self.pick_btn = ttk.Button(b, text="Alege…", command=self._pick)
        self.pick_btn.grid(row=0, column=2, padx=4)
        if session:
            self.pick_btn.state(["disabled"])
        now_local = utc_to_local(session.start_at, tz) if session else datetime.now(app.q.tz()) + timedelta(hours=1)
        end_local = utc_to_local(session.end_at, tz) if session else now_local + timedelta(hours=1)
        self.date_var = tk.StringVar(value=format_date(now_local.date()))
        self.start_var = tk.StringVar(value=f"{now_local:%H:%M}" if session else f"{now_local.hour:02d}:00")
        self.end_var = tk.StringVar(value=f"{end_local:%H:%M}" if session else f"{(now_local.hour + 1) % 24:02d}:00")
        self.dur_var = tk.StringVar()
        ttk.Label(b, text="Data").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.date_var, width=14).grid(row=1, column=1, sticky="w")
        ttk.Label(b, text="Început").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.start_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(b, text="Sfârșit sau durată").grid(row=3, column=0, sticky="w", pady=4)
        fr = ttk.Frame(b)
        fr.grid(row=3, column=1, sticky="w")
        ttk.Entry(fr, textvariable=self.end_var, width=8).pack(side="left")
        ttk.Label(fr, text="  sau durată").pack(side="left")
        ttk.Entry(fr, textvariable=self.dur_var, width=8).pack(side="left", padx=4)
        ttk.Label(b, text="Notiță").grid(row=4, column=0, sticky="w", pady=4)
        self.note_var = tk.StringVar(value=(session.note or "") if session else "")
        ttk.Entry(b, textvariable=self.note_var).grid(row=4, column=1, columnspan=2, sticky="ew")
        self.reserve_var = tk.BooleanVar(value=session.reserve_calendar if session else False)
        ttk.Checkbutton(b, text="Rezervă timp în calendar (Outlook / export ICS)", variable=self.reserve_var).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(b, style="Muted.TLabel", wraplength=420, text=(
            "Timpul planificat nu este timp lucrat; doar sesiunile pornite și oprite cu timerul contează ca lucrat. "
            f"Fus orar: {tz}.")).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._refresh_task()

    def _refresh_task(self) -> None:
        n = self.app.ws.nodes.get(self.node_id) if self.node_id else None
        self.task_lbl.configure(text=n.title if n else "(alege un task)")

    def _pick(self) -> None:
        picked = NodePickerDialog(self, self.app.ws, "Alege task-ul", only_tasks=True).run()
        if picked:
            self.node_id = picked
            self._refresh_task()

    def _compute(self) -> tuple[datetime, datetime]:
        tz = self.app.ws.settings.timezone
        day = parse_date(self.date_var.get(), self.app.q.today())
        st = parse_time(self.start_var.get())
        if day is None or st is None:
            raise ValueError("Data și ora de început sunt obligatorii.")
        start = local_to_utc(day, st, tz)
        dur = parse_duration(self.dur_var.get())
        if dur:
            return start, start + timedelta(minutes=dur)
        en = parse_time(self.end_var.get())
        if en is None:
            raise ValueError("Introdu ora de sfârșit sau o durată.")
        end = local_to_utc(day, en, tz)
        return start, end

    def validate(self) -> bool:
        if not self.node_id:
            show_error(self, "Alege un task.")
            return False
        try:
            self._start, self._end = self._compute()
        except (ValueError, AmbiguousLocalTime) as exc:
            show_error(self, str(exc))
            return False
        return True

    def collect(self):
        svc = self.app.sessions
        allow_overlap = override = False
        for _ in range(3):
            try:
                if self.session:
                    res = svc.update(self.session.id, start=self._start, end=self._end, note=self.note_var.get(),
                                     reserve_calendar=self.reserve_var.get(), allow_overlap=allow_overlap)
                else:
                    res = svc.create(self.node_id, self._start, self._end, note=self.note_var.get(),
                                     reserve_calendar=self.reserve_var.get(), allow_overlap=allow_overlap,
                                     override_dependencies=override)
                self.app.status.set_saved()
                return res
            except OverlapError as exc:
                names = ", ".join(self.app.ws.nodes[c.node_id].title for c in exc.conflicts if c.node_id in self.app.ws.nodes)
                if not confirm(self, f"Intervalul se suprapune cu: {names}.\nProgramez oricum?"):
                    return False
                allow_overlap = True
            except BlockedByDependencies as exc:
                if not confirm(self, f"{exc}\n\nProgramez oricum (suprascriere explicită)?"):
                    return False
                override = True
            except FocusDeskError as exc:
                show_error(self, str(exc))
                return False
        return False


class PlannerDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", preselected: list[str] | None = None) -> None:
        super().__init__(parent, "Planificare asistată", resizable=True, ok_text="Aplică selectate",
                         cancel_text="Renunță")
        self.app = app
        self.q = app.q
        self.result_data = None
        self.proposals: list[ProposedSession] = []
        self.checked: set[int] = set()
        self._job = None
        self.geometry("980x760")
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        today = self.q.today()
        self.from_var = tk.StringVar(value=format_date(today))
        self.to_var = tk.StringVar(value=format_date(today + timedelta(days=6)))
        ttk.Label(top, text="De la").pack(side="left")
        ttk.Entry(top, textvariable=self.from_var, width=12).pack(side="left", padx=(4, 12))
        ttk.Label(top, text="Până la").pack(side="left")
        ttk.Entry(top, textvariable=self.to_var, width=12).pack(side="left", padx=(4, 12))
        self.filter_var = tk.StringVar()
        ttk.Label(top, text="Filtru").pack(side="left")
        ttk.Entry(top, textvariable=self.filter_var, width=20).pack(side="left", padx=4)
        self.filter_var.trace_add("write", lambda *_: self._fill_tasks())
        ttk.Label(self.body, text="1. Alege task-urile (Ctrl/Shift pentru mai multe) și verifică estimările",
                  style="Section.TLabel").pack(anchor="w", pady=(8, 2))
        self.tasks_tv, frame = make_tree(self.body, [("title", "Task", 300), ("est", "Timp rămas", 90),
                                                     ("due", "Termen", 90), ("prio", "Prioritate", 80),
                                                     ("note", "Observație", 200)], height=8, selectmode="extended")
        frame.pack(fill="x")
        est = ttk.Frame(self.body)
        est.pack(fill="x", pady=4)
        ttk.Label(est, text="Estimare pentru selectate:").pack(side="left")
        self.est_var = tk.StringVar()
        ttk.Entry(est, textvariable=self.est_var, width=9).pack(side="left", padx=4)
        ttk.Button(est, text="Setează estimarea", command=self._set_estimate).pack(side="left")
        ttk.Label(est, text="(se salvează în task; nu inventăm estimări)", style="Muted.TLabel").pack(side="left", padx=8)
        self.calc_btn = tb.Button(self.body, text="2. Calculează propunerea", command=self._calculate,
                                  bootstyle="primary")
        self.calc_btn.pack(anchor="w", pady=(6, 2))
        self.note_lbl = ttk.Label(self.body, text="", style="Muted.TLabel", wraplength=900, justify="left")
        self.note_lbl.pack(anchor="w")
        ttk.Label(self.body, text="3. Previzualizare (dublu-clic comută includerea)", style="Section.TLabel").pack(
            anchor="w", pady=(6, 2))
        self.prop_tv, f2 = make_tree(self.body, [("use", "✓", 30), ("task", "Task", 300), ("day", "Data", 100),
                                                 ("span", "Interval", 120), ("dur", "Durată", 80)], height=8)
        f2.pack(fill="both", expand=True)
        self.prop_tv.bind("<Double-1>", self._toggle)
        self.un_tv, f3 = make_tree(self.body, [("task", "Nealocat", 300), ("miss", "Lipsă", 90),
                                               ("why", "Motiv", 420)], height=4)
        f3.pack(fill="x", pady=(6, 0))
        self.reserve_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.body, text="Rezervări personale de timp în calendar (Outlook/ICS), fără invitați sau Teams",
                        variable=self.reserve_var).pack(anchor="w", pady=(6, 0))
        self._pre = set(preselected or [])
        self._fill_tasks()

    # ---- tasks ------------------------------------------------------
    def _fill_tasks(self) -> None:
        q = self.q
        selected = set(self.tasks_tv.selection()) | self._pre
        self._pre = set()
        self.tasks_tv.delete(*self.tasks_tv.get_children())
        text = self.filter_var.get().strip().lower()
        tasks = [n for n in q.tasks() if n.status not in CLOSED_STATUSES and (not text or text in n.title.lower())]
        for n in q._sorted(tasks)[:500]:
            rem = n.remaining_minutes if n.remaining_minutes is not None else n.estimated_minutes
            blockers = self.app.ws.unfinished_dependencies(n.id)
            obs = "Neestimat" if rem is None else ""
            if blockers:
                obs = (obs + "; " if obs else "") + "blocat de " + ", ".join(b.title for b in blockers[:2])
            self.tasks_tv.insert("", "end", iid=n.id, values=(
                n.title, format_minutes(rem), format_date(q.due_day(n)),
                PRIORITY_LABELS.get(n.priority or Priority.NORMAL, ""), obs))
        keep = [s for s in selected if self.tasks_tv.exists(s)]
        if keep:
            self.tasks_tv.selection_set(keep)

    def _set_estimate(self) -> None:
        try:
            minutes = parse_duration(self.est_var.get())
        except ValueError as exc:
            show_error(self, str(exc))
            return
        if minutes is None:
            return
        sel = list(self.tasks_tv.selection())
        if not sel:
            show_info(self, "Selectează task-urile pentru care setezi estimarea.")
            return
        ok = self.app.run_write(lambda: [self.app.ws.update_node(n, estimated_minutes=minutes, remaining_minutes=minutes)
                                         for n in sel])
        if ok:
            self._fill_tasks()

    # ---- calculation ------------------------------------------------
    def _period(self) -> tuple[date, date]:
        a = parse_date(self.from_var.get(), self.q.today())
        b = parse_date(self.to_var.get(), self.q.today())
        if a is None or b is None or b < a:
            raise ValueError("Perioada este invalidă.")
        if (b - a).days > 92:
            raise ValueError("Perioada maximă este de 92 de zile.")
        return a, b

    def _calculate(self) -> None:
        try:
            a, b = self._period()
        except ValueError as exc:
            show_error(self, str(exc))
            return
        sel = list(self.tasks_tv.selection())
        if not sel:
            show_info(self, "Selectează cel puțin un task.")
            return
        self.calc_btn.state(["disabled"])
        self.note_lbl.configure(text="Se verifică disponibilitatea…")

        def got(av) -> None:
            self.calc_btn.state(["!disabled"])
            result = self.app.planning.plan([PlanRequest(i) for i in sel], a, b, av)
            self._show(result)

        def failed(exc: BaseException) -> None:
            self.calc_btn.state(["!disabled"])
            self.note_lbl.configure(text=f"Disponibilitatea nu a putut fi citită: {exc}")

        self.app.get_availability(a, b, got, failed)

    def _show(self, result) -> None:
        tz = self.app.ws.settings.timezone
        self.proposals = result.sessions
        self.checked = set(range(len(self.proposals)))
        self.prop_tv.delete(*self.prop_tv.get_children())
        for i, p in enumerate(self.proposals):
            self._insert_prop(i, p, tz)
        self.un_tv.delete(*self.un_tv.get_children())
        for u in result.unallocated:
            n = self.app.ws.nodes.get(u.node_id)
            self.un_tv.insert("", "end", values=(n.title if n else u.node_id[:8],
                                                 format_minutes(u.minutes_missing) if u.minutes_missing else "—",
                                                 u.reason))
        total = sum(p.minutes for p in self.proposals)
        notes = " ".join(result.notes)
        self.note_lbl.configure(text=f"{len(self.proposals)} sesiuni propuse, {format_minutes(total)}. "
                                     f"Timp liber în perioadă: {format_minutes(result.free_minutes_total)}. {notes}")

    def _insert_prop(self, i: int, p: ProposedSession, tz: str) -> None:
        n = self.app.ws.nodes.get(p.node_id)
        a, b = utc_to_local(p.start, tz), utc_to_local(p.end, tz)
        self.prop_tv.insert("", "end", iid=str(i), values=(
            "☑" if i in self.checked else "☐", n.title if n else "?", format_date(a.date()),
            f"{a:%H:%M}–{b:%H:%M}", format_minutes(p.minutes)))

    def _toggle(self, event: tk.Event) -> None:
        iid = self.prop_tv.identify_row(event.y)
        if not iid:
            return
        i = int(iid)
        if i in self.checked:
            self.checked.discard(i)
        else:
            self.checked.add(i)
        vals = list(self.prop_tv.item(iid, "values"))
        vals[0] = "☑" if i in self.checked else "☐"
        self.prop_tv.item(iid, values=vals)

    # ---- apply ------------------------------------------------------
    def validate(self) -> bool:
        if not self.checked:
            show_error(self, "Nu există propuneri selectate. Calculează propunerea și bifează sesiunile dorite.")
            return False
        return True

    def collect(self):
        chosen = [self.proposals[i] for i in sorted(self.checked)]
        out = self.app.planning.apply(chosen, reserve_calendar=self.reserve_var.get())
        msg = f"{len(out.created)} sesiuni create."
        if out.failed:
            msg += f"\n{len(out.failed)} nu au putut fi aplicate:\n" + "\n".join(
                f"• {self.app.ws.nodes[p.node_id].title if p.node_id in self.app.ws.nodes else '?'}: {why}"
                for p, why in out.failed[:8])
        show_info(self, msg, "Planificare")
        return out


class RecurrenceDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, "Task-uri recurente", resizable=True, ok_text="Închide", cancel_text="Închide")
        self.ok_btn.pack_forget()
        self.app = app
        self.svc = app.recurrence
        self.tv, frame = make_tree(self.body, [("title", "Șablon", 220), ("rule", "Regulă", 160), ("start", "De la", 90),
                                               ("est", "Estimare", 70), ("act", "Activ", 50)], height=8)
        frame.pack(fill="both", expand=True)
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        for text, cmd in (("Nou…", self._new), ("Activează / dezactivează", self._toggle), ("Șterge șablonul", self._delete),
                          ("Generează instanța de azi", self._gen_today)):
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=2)
        ttk.Label(self.body, style="Muted.TLabel", wraplength=560, text=(
            "Instanțele sunt task-uri independente, create cu cheia unică (șablon, dată). Ștergerea șablonului nu "
            "șterge task-urile deja generate. Zilele ratate nu se generează automat: le alegi tu.")).pack(anchor="w")
        self._load()

    def _load(self) -> None:
        self.tv.delete(*self.tv.get_children())
        for t in self.svc.templates():
            rule = {"daily": "Zilnic", "workdays": "Zile lucrătoare",
                    "weekly": "Săptămânal: " + ", ".join(WEEKDAYS[d] for d in t.weekdays)}[t.frequency]
            self.tv.insert("", "end", iid=t.id, values=(t.title, rule, format_date(t.start_date),
                                                       duration_to_text(t.estimated_minutes), "da" if t.active else "nu"))

    def _sel(self) -> str | None:
        s = self.tv.selection()
        return s[0] if s else None

    def _new(self) -> None:
        res = NewRecurrenceDialog(self, self.app).run()
        if res and self.app.run_write(lambda: self.svc.create(**res)):
            self._load()

    def _toggle(self) -> None:
        t = self._sel()
        if t:
            cur = self.app.ws.repo.recurrences.get(t)
            self.app.run_write(lambda: self.svc.set_active(t, not cur.active))
            self._load()

    def _delete(self) -> None:
        t = self._sel()
        if t and confirm(self, "Ștergi șablonul? Task-urile deja generate rămân."):
            self.app.run_write(lambda: self.svc.delete(t))
            self._load()

    def _gen_today(self) -> None:
        t = self._sel()
        if not t:
            return
        today = self.app.q.today()
        made: list = []
        if self.app.run_write(lambda: made.append(self.svc.generate(t, today))):
            show_info(self, "Instanța a fost creată." if made and made[0] else "Instanța există deja pentru azi.")
            self.app.refresh_all()


class NewRecurrenceDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, "Șablon recurent nou", ok_text="Creează")
        self.app = app
        b = self.body
        b.columnconfigure(1, weight=1)
        self.title_var = tk.StringVar()
        ttk.Label(b, text="Titlu").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(b, textvariable=self.title_var, width=44).grid(row=0, column=1, sticky="ew")
        self._choices = location_choices(app.ws, Kind.TASK)
        ttk.Label(b, text="Locație").grid(row=1, column=0, sticky="w", pady=3)
        self.loc = ttk.Combobox(b, state="readonly", values=[c[0] for c in self._choices])
        self.loc.grid(row=1, column=1, sticky="ew")
        self.loc.current(0)
        ttk.Label(b, text="Regulă").grid(row=2, column=0, sticky="w", pady=3)
        self.freq = ttk.Combobox(b, state="readonly", values=["Zilnic", "Zile lucrătoare", "Săptămânal"])
        self.freq.grid(row=2, column=1, sticky="w")
        self.freq.current(1)
        self.day_vars = [tk.BooleanVar() for _ in range(7)]
        days = ttk.Frame(b)
        days.grid(row=3, column=1, sticky="w")
        for i, v in enumerate(self.day_vars):
            ttk.Checkbutton(days, text=WEEKDAYS[i], variable=v).pack(side="left")
        ttk.Label(b, text="Începe la").grid(row=4, column=0, sticky="w", pady=3)
        self.start_var = tk.StringVar(value=format_date(app.q.today()))
        ttk.Entry(b, textvariable=self.start_var, width=14).grid(row=4, column=1, sticky="w")
        ttk.Label(b, text="Estimare").grid(row=5, column=0, sticky="w", pady=3)
        self.est_var = tk.StringVar()
        ttk.Entry(b, textvariable=self.est_var, width=10).grid(row=5, column=1, sticky="w")
        ttk.Label(b, text="Etichete").grid(row=6, column=0, sticky="w", pady=3)
        self.tags_var = tk.StringVar()
        ttk.Entry(b, textvariable=self.tags_var).grid(row=6, column=1, sticky="ew")

    def validate(self) -> bool:
        if not self.title_var.get().strip():
            show_error(self, "Titlul este obligatoriu.")
            return False
        try:
            parse_date(self.start_var.get())
            parse_duration(self.est_var.get())
        except ValueError as exc:
            show_error(self, str(exc))
            return False
        return True

    def collect(self) -> dict:
        freq = {"Zilnic": "daily", "Zile lucrătoare": "workdays", "Săptămânal": "weekly"}[self.freq.get()]
        return dict(title=self.title_var.get().strip(), parent_id=self._choices[self.loc.current()][1], frequency=freq,
                    weekdays=[i for i, v in enumerate(self.day_vars) if v.get()],
                    start_date=parse_date(self.start_var.get()) or self.app.q.today(),
                    estimated_minutes=parse_duration(self.est_var.get()), tags=parse_tags(self.tags_var.get()))


class MissedRecurrenceDialog(ModalDialog):
    """Instante ratate: utilizatorul alege ce se genereaza; restul se sar."""

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", missed: dict[str, list[date]]) -> None:
        super().__init__(parent, "Instanțe recurente ratate", resizable=True, ok_text="Generează selectate",
                         cancel_text="Mai târziu")
        self.app = app
        self.missed = missed
        ttk.Label(self.body, wraplength=560, text=(
            "Aplicația nu a rulat în aceste zile. Nimic nu s-a generat automat. Selectează instanțele pe care le vrei; "
            "cele neselectate rămân disponibile sau poți alege „Sari peste”.")).pack(anchor="w")
        self.tv, frame = make_tree(self.body, [("tpl", "Șablon", 260), ("day", "Data", 110)], height=12,
                                   selectmode="extended")
        frame.pack(fill="both", expand=True, pady=6)
        for tid, days in missed.items():
            t = app.ws.repo.recurrences.get(tid)
            for d in days:
                self.tv.insert("", "end", iid=f"{tid}|{d.isoformat()}", values=(t.title, format_date(d)))
        skip = ttk.Button(self.buttons, text="Sari peste cele selectate", command=self._skip)
        skip.pack(side="left")

    def _items(self) -> list[tuple[str, date]]:
        return [(i.split("|")[0], date.fromisoformat(i.split("|")[1])) for i in self.tv.selection()]

    def _skip(self) -> None:
        items = self._items()
        if not items:
            return
        by: dict[str, list[date]] = {}
        for t, d in items:
            by.setdefault(t, []).append(d)
        self.app.run_write(lambda: [self.app.recurrence.skip(t, ds) for t, ds in by.items()])
        for i in self.tv.selection():
            self.tv.delete(i)

    def collect(self):
        items = self._items()
        created = []

        def work() -> None:
            for t, d in items:
                n = self.app.recurrence.generate(t, d)
                if n:
                    created.append(n)

        self.app.run_write(work)
        return created
