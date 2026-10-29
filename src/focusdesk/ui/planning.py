"""Dialoguri de planificare: programare manuala, planificare asistata, recurente."""

from __future__ import annotations

from ..i18n import datetime_text

from ..i18n import tr

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

WEEKDAYS = [tr('ui.planning.lu'), tr('ui.planning.ma'), tr('ui.planning.mi'), tr('ui.planning.jo'), tr('ui.planning.vi'), tr('ui.planning.sa'), tr('ui.planning.du')]


def sync_state_text(s: SessionRecord) -> str:
    st = s.sync.state
    if st == "none":
        return "—"
    if st == "exported":
        text = EXPORT_STATE_TEXT
        if s.sync.signature and s.sync.signature != session_signature(s):
            text += tr('ui.planning.modificat_dupa_export')
        return text
    return {
        "pending": tr('ui.planning.in_asteptare_nesincronizat'),
        "saved_locally": tr('ui.planning.salvat_in_outlook_local_sincronizarea_exchange_neconfirmata'),
        "failed": tr('ui.planning.esuat') + (f": {s.sync.error}" if s.sync.error else ""),
        "conflict": tr('ui.planning.conflict_cu_outlook'),
        "detached": tr('ui.planning.detasat_de_calendar'),
        "cancelled": tr('ui.planning.anulat'),
    }.get(st, st)


def fmt_range(s: SessionRecord, tz: str) -> str:
    a, b = utc_to_local(s.start_at, tz), utc_to_local(s.end_at, tz)
    return f'{datetime_text(a)}–{b:%H:%M}'


class ManualSessionDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", node_id: str | None = None,
                 session: SessionRecord | None = None) -> None:
        super().__init__(parent, tr('ui.planning.modifica_sesiunea') if session else tr('ui.planning.programeaza_sesiune'),
                         ok_text=tr('ui.settings_dialog.salveaza') if session else tr('ui.planning.programeaza'))
        self.app = app
        self.session = session
        tz = app.ws.settings.timezone
        self.node_id = session.node_id if session else node_id
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text=tr('ui.outlook_ui.task')).grid(row=0, column=0, sticky="w", pady=4)
        self.task_lbl = ttk.Label(b, text=tr('ui.planning.alege_un_task'), width=42)
        self.task_lbl.grid(row=0, column=1, sticky="w")
        self.pick_btn = ttk.Button(b, text=tr('common.choose'), command=self._pick)
        self.pick_btn.grid(row=0, column=2, padx=4)
        if session:
            self.pick_btn.state(["disabled"])
        now_local = utc_to_local(session.start_at, tz) if session else datetime.now(app.q.tz()) + timedelta(hours=1)
        end_local = utc_to_local(session.end_at, tz) if session else now_local + timedelta(hours=1)
        self.date_var = tk.StringVar(value=format_date(now_local.date()))
        self.start_var = tk.StringVar(value=f"{now_local:%H:%M}" if session else f"{now_local.hour:02d}:00")
        self.end_var = tk.StringVar(value=f"{end_local:%H:%M}" if session else f"{(now_local.hour + 1) % 24:02d}:00")
        self.dur_var = tk.StringVar()
        ttk.Label(b, text=tr('ui.tab_versions.data')).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.date_var, width=14).grid(row=1, column=1, sticky="w")
        ttk.Label(b, text=tr('ui.planning.inceput')).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.start_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(b, text=tr('ui.planning.sfarsit_sau_durata')).grid(row=3, column=0, sticky="w", pady=4)
        fr = ttk.Frame(b)
        fr.grid(row=3, column=1, sticky="w")
        ttk.Entry(fr, textvariable=self.end_var, width=8).pack(side="left")
        ttk.Label(fr, text=tr('ui.planning.sau_durata')).pack(side="left")
        ttk.Entry(fr, textvariable=self.dur_var, width=8).pack(side="left", padx=4)
        ttk.Label(b, text=tr('ui.tab_journal.notita')).grid(row=4, column=0, sticky="w", pady=4)
        self.note_var = tk.StringVar(value=(session.note or "") if session else "")
        ttk.Entry(b, textvariable=self.note_var).grid(row=4, column=1, columnspan=2, sticky="ew")
        self.reserve_var = tk.BooleanVar(value=session.reserve_calendar if session else False)
        ttk.Checkbutton(b, text=tr('ui.planning.rezerva_timp_in_calendar_outlook_export_ics'), variable=self.reserve_var).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(b, style="Muted.TLabel", wraplength=420, text=(
            tr('ui.planning.timpul_planificat_nu_este_timp_lucrat_doar_sesiunile_pornite_si_oprite', tz=tz))).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._refresh_task()

    def _refresh_task(self) -> None:
        n = self.app.ws.nodes.get(self.node_id) if self.node_id else None
        self.task_lbl.configure(text=n.title if n else tr('ui.planning.alege_un_task'))

    def _pick(self) -> None:
        picked = NodePickerDialog(self, self.app.ws, tr('ui.planning.alege_task_ul'), only_tasks=True).run()
        if picked:
            self.node_id = picked
            self._refresh_task()

    def _compute(self) -> tuple[datetime, datetime]:
        tz = self.app.ws.settings.timezone
        day = parse_date(self.date_var.get(), self.app.q.today())
        st = parse_time(self.start_var.get())
        if day is None or st is None:
            raise ValueError(tr('ui.planning.data_si_ora_de_inceput_sunt_obligatorii'))
        start = local_to_utc(day, st, tz)
        dur = parse_duration(self.dur_var.get())
        if dur:
            return start, start + timedelta(minutes=dur)
        en = parse_time(self.end_var.get())
        if en is None:
            raise ValueError(tr('ui.planning.introdu_ora_de_sfarsit_sau_o_durata'))
        end = local_to_utc(day, en, tz)
        return start, end

    def validate(self) -> bool:
        if not self.node_id:
            show_error(self, tr('ui.planning.alege_un_task_2'))
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
                if not confirm(self, tr('ui.planning.intervalul_se_suprapune_cu_programez_oricum', names=names)):
                    return False
                allow_overlap = True
            except BlockedByDependencies as exc:
                if not confirm(self, tr('ui.planning.programez_oricum_suprascriere_explicita', exc=exc)):
                    return False
                override = True
            except FocusDeskError as exc:
                show_error(self, str(exc))
                return False
        return False


class PlannerDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", preselected: list[str] | None = None) -> None:
        super().__init__(parent, tr('ui.planning.planificare_asistata'), resizable=True, ok_text=tr('ui.planning.aplica_selectate'),
                         cancel_text=tr('ui.planning.renunta'))
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
        ttk.Label(top, text=tr('ui.meetings.de_la')).pack(side="left")
        ttk.Entry(top, textvariable=self.from_var, width=12).pack(side="left", padx=(4, 12))
        ttk.Label(top, text=tr('ui.meetings.pana_la')).pack(side="left")
        ttk.Entry(top, textvariable=self.to_var, width=12).pack(side="left", padx=(4, 12))
        self.filter_var = tk.StringVar()
        ttk.Label(top, text=tr('ui.planning.filtru')).pack(side="left")
        ttk.Entry(top, textvariable=self.filter_var, width=20).pack(side="left", padx=4)
        self.filter_var.trace_add("write", lambda *_: self._fill_tasks())
        ttk.Label(self.body, text=tr('ui.planning.1_alege_task_urile_ctrl_shift_pentru_mai_multe_si_verifica_estimarile'),
                  style="Section.TLabel").pack(anchor="w", pady=(8, 2))
        self.tasks_tv, frame = make_tree(self.body, [("title", tr('ui.outlook_ui.task'), 300), ("est", tr('ui.planning.timp_ramas'), 90),
                                                     ("due", tr('ui.meetings.termen'), 90), ("prio", tr('ui.meetings.prioritate'), 80),
                                                     ("note", tr('ui.planning.observatie'), 200)], height=8, selectmode="extended")
        frame.pack(fill="x")
        est = ttk.Frame(self.body)
        est.pack(fill="x", pady=4)
        ttk.Label(est, text=tr('ui.planning.estimare_pentru_selectate')).pack(side="left")
        self.est_var = tk.StringVar()
        ttk.Entry(est, textvariable=self.est_var, width=9).pack(side="left", padx=4)
        ttk.Button(est, text=tr('ui.planning.seteaza_estimarea'), command=self._set_estimate).pack(side="left")
        ttk.Label(est, text=tr('ui.planning.se_salveaza_in_task_nu_inventam_estimari'), style="Muted.TLabel").pack(side="left", padx=8)
        self.calc_btn = tb.Button(self.body, text=tr('ui.planning.2_calculeaza_propunerea'), command=self._calculate,
                                  bootstyle="primary")
        self.calc_btn.pack(anchor="w", pady=(6, 2))
        self.note_lbl = ttk.Label(self.body, text="", style="Muted.TLabel", wraplength=900, justify="left")
        self.note_lbl.pack(anchor="w")
        ttk.Label(self.body, text=tr('ui.planning.3_previzualizare_dublu_clic_comuta_includerea'), style="Section.TLabel").pack(
            anchor="w", pady=(6, 2))
        self.prop_tv, f2 = make_tree(self.body, [("use", "✓", 30), ("task", tr('ui.outlook_ui.task'), 300), ("day", tr('ui.tab_versions.data'), 100),
                                                 ("span", tr('ui.planning.interval'), 120), ("dur", tr('ui.planning.durata'), 80)], height=8)
        f2.pack(fill="both", expand=True)
        self.prop_tv.bind("<Double-1>", self._toggle)
        self.un_tv, f3 = make_tree(self.body, [("task", tr('ui.planning.nealocat'), 300), ("miss", tr('ui.planning.lipsa'), 90),
                                               ("why", tr('ui.outlook_ui.motiv'), 420)], height=4)
        f3.pack(fill="x", pady=(6, 0))
        self.reserve_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.body, text=tr('ui.planning.rezervari_personale_de_timp_in_calendar_outlook_ics_fara_invitati_sau'),
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
            obs = tr('ui.planning.neestimat') if rem is None else ""
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
            show_info(self, tr('ui.planning.selecteaza_task_urile_pentru_care_setezi_estimarea'))
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
            raise ValueError(tr('ui.planning.perioada_este_invalida'))
        if (b - a).days > 92:
            raise ValueError(tr('ui.planning.perioada_maxima_este_de_92_de_zile'))
        return a, b

    def _calculate(self) -> None:
        try:
            a, b = self._period()
        except ValueError as exc:
            show_error(self, str(exc))
            return
        sel = list(self.tasks_tv.selection())
        if not sel:
            show_info(self, tr('ui.planning.selecteaza_cel_putin_un_task'))
            return
        self.calc_btn.state(["disabled"])
        self.note_lbl.configure(text=tr('ui.planning.se_verifica_disponibilitatea'))

        def got(av) -> None:
            self.calc_btn.state(["!disabled"])
            result = self.app.planning.plan([PlanRequest(i) for i in sel], a, b, av)
            self._show(result)

        def failed(exc: BaseException) -> None:
            self.calc_btn.state(["!disabled"])
            self.note_lbl.configure(text=tr('ui.planning.disponibilitatea_nu_a_putut_fi_citita', exc=exc))

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
        self.note_lbl.configure(text=tr('ui.planning.sesiuni_propuse_timp_liber_in_perioada', len_self_proposals=len(self.proposals), format_minutes_total=format_minutes(total), format_minutes_result_free_minutes_total=format_minutes(result.free_minutes_total), notes=notes))

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
            show_error(self, tr('ui.planning.nu_exista_propuneri_selectate_calculeaza_propunerea_si_bifeaza_sesiuni'))
            return False
        return True

    def collect(self):
        chosen = [self.proposals[i] for i in sorted(self.checked)]
        out = self.app.planning.apply(chosen, reserve_calendar=self.reserve_var.get())
        msg = tr('ui.planning.sesiuni_create', count=len(out.created), len_out_created=len(out.created))
        if out.failed:
            msg += tr('ui.planning.nu_au_putut_fi_aplicate', len_out_failed=len(out.failed)) + "\n".join(
                tr('ui.planning.unallocated_reason', _title_if_p_node_id_in_self_app_ws_nodes_else=self.app.ws.nodes[p.node_id].title if p.node_id in self.app.ws.nodes else '?', why=why)
                for p, why in out.failed[:8])
        show_info(self, msg, tr('ui.planning.planificare'))
        return out


class RecurrenceDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, "Task-uri recurente", resizable=True, ok_text=tr('ui.outlook_ui.inchide'), cancel_text=tr('ui.outlook_ui.inchide'))
        self.ok_btn.pack_forget()
        self.app = app
        self.svc = app.recurrence
        self.tv, frame = make_tree(self.body, [("title", tr('ui.planning.sablon'), 220), ("rule", tr('ui.planning.regula'), 160), ("start", tr('ui.meetings.de_la'), 90),
                                               ("est", tr('ui.tab_details.estimare'), 70), ("act", tr('ui.planning.activ'), 50)], height=8)
        frame.pack(fill="both", expand=True)
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        for text, cmd in (("Nou…", self._new), (tr('ui.planning.activeaza_dezactiveaza'), self._toggle), (tr('ui.planning.sterge_sablonul'), self._delete),
                          (tr('ui.planning.genereaza_instanta_de_azi'), self._gen_today)):
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=2)
        ttk.Label(self.body, style="Muted.TLabel", wraplength=560, text=(
            tr('ui.planning.instantele_sunt_task_uri_independente_create_cu_cheia_unica_sablon_dat'))).pack(anchor="w")
        self._load()

    def _load(self) -> None:
        self.tv.delete(*self.tv.get_children())
        for t in self.svc.templates():
            rule = {"daily": tr('ui.planning.zilnic'), "workdays": tr('ui.planning.zile_lucratoare'),
                    "weekly": tr('ui.planning.saptamanal_2') + ", ".join(WEEKDAYS[d] for d in t.weekdays)}[t.frequency]
            self.tv.insert("", "end", iid=t.id, values=(t.title, rule, format_date(t.start_date),
                                                       duration_to_text(t.estimated_minutes), tr('common.yes') if t.active else tr('common.no')))

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
        if t and confirm(self, tr('ui.planning.stergi_sablonul_task_urile_deja_generate_raman')):
            self.app.run_write(lambda: self.svc.delete(t))
            self._load()

    def _gen_today(self) -> None:
        t = self._sel()
        if not t:
            return
        today = self.app.q.today()
        made: list = []
        if self.app.run_write(lambda: made.append(self.svc.generate(t, today))):
            show_info(self, tr('ui.planning.instanta_a_fost_creata') if made and made[0] else tr('ui.planning.instanta_exista_deja_pentru_azi'))
            self.app.refresh_all()


class NewRecurrenceDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, tr('ui.planning.sablon_recurent_nou'), ok_text=tr('ui.planning.creeaza'))
        self.app = app
        b = self.body
        b.columnconfigure(1, weight=1)
        self.title_var = tk.StringVar()
        ttk.Label(b, text=tr('ui.meetings.titlu')).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(b, textvariable=self.title_var, width=44).grid(row=0, column=1, sticky="ew")
        self._choices = location_choices(app.ws, Kind.TASK)
        ttk.Label(b, text=tr('ui.dashboard.locatie')).grid(row=1, column=0, sticky="w", pady=3)
        self.loc = ttk.Combobox(b, state="readonly", values=[c[0] for c in self._choices])
        self.loc.grid(row=1, column=1, sticky="ew")
        self.loc.current(0)
        ttk.Label(b, text=tr('ui.planning.regula')).grid(row=2, column=0, sticky="w", pady=3)
        self.freq = ttk.Combobox(b, state="readonly", values=[tr('ui.planning.zilnic'), tr('ui.planning.zile_lucratoare'), tr('ui.planning.saptamanal')])
        self.freq.grid(row=2, column=1, sticky="w")
        self.freq.current(1)
        self.day_vars = [tk.BooleanVar() for _ in range(7)]
        days = ttk.Frame(b)
        days.grid(row=3, column=1, sticky="w")
        for i, v in enumerate(self.day_vars):
            ttk.Checkbutton(days, text=WEEKDAYS[i], variable=v).pack(side="left")
        ttk.Label(b, text=tr('ui.planning.incepe_la')).grid(row=4, column=0, sticky="w", pady=3)
        self.start_var = tk.StringVar(value=format_date(app.q.today()))
        ttk.Entry(b, textvariable=self.start_var, width=14).grid(row=4, column=1, sticky="w")
        ttk.Label(b, text=tr('ui.tab_details.estimare')).grid(row=5, column=0, sticky="w", pady=3)
        self.est_var = tk.StringVar()
        ttk.Entry(b, textvariable=self.est_var, width=10).grid(row=5, column=1, sticky="w")
        ttk.Label(b, text=tr('ui.tab_details.etichete')).grid(row=6, column=0, sticky="w", pady=3)
        self.tags_var = tk.StringVar()
        ttk.Entry(b, textvariable=self.tags_var).grid(row=6, column=1, sticky="ew")

    def validate(self) -> bool:
        if not self.title_var.get().strip():
            show_error(self, tr('ui.planning.titlul_este_obligatoriu'))
            return False
        try:
            parse_date(self.start_var.get())
            parse_duration(self.est_var.get())
        except ValueError as exc:
            show_error(self, str(exc))
            return False
        return True

    def collect(self) -> dict:
        freq = {tr('ui.planning.zilnic'): "daily", tr('ui.planning.zile_lucratoare'): "workdays", tr('ui.planning.saptamanal'): "weekly"}[self.freq.get()]
        return dict(title=self.title_var.get().strip(), parent_id=self._choices[self.loc.current()][1], frequency=freq,
                    weekdays=[i for i, v in enumerate(self.day_vars) if v.get()],
                    start_date=parse_date(self.start_var.get()) or self.app.q.today(),
                    estimated_minutes=parse_duration(self.est_var.get()), tags=parse_tags(self.tags_var.get()))


class MissedRecurrenceDialog(ModalDialog):
    """Instante ratate: utilizatorul alege ce se genereaza; restul se sar."""

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", missed: dict[str, list[date]]) -> None:
        super().__init__(parent, tr('ui.planning.instante_recurente_ratate'), resizable=True, ok_text=tr('ui.planning.genereaza_selectate'),
                         cancel_text=tr('ui.planning.mai_tarziu'))
        self.app = app
        self.missed = missed
        ttk.Label(self.body, wraplength=560, text=(
            tr('ui.planning.aplicatia_nu_a_rulat_in_aceste_zile_nimic_nu_s_a_generat_automat_selec'))).pack(anchor="w")
        self.tv, frame = make_tree(self.body, [("tpl", tr('ui.planning.sablon'), 260), ("day", tr('ui.tab_versions.data'), 110)], height=12,
                                   selectmode="extended")
        frame.pack(fill="both", expand=True, pady=6)
        for tid, days in missed.items():
            t = app.ws.repo.recurrences.get(tid)
            for d in days:
                self.tv.insert("", "end", iid=f"{tid}|{d.isoformat()}", values=(t.title, format_date(d)))
        skip = ttk.Button(self.buttons, text=tr('ui.planning.sari_peste_cele_selectate'), command=self._skip)
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
