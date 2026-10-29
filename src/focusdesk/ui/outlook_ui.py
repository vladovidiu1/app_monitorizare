"""Integrarea Outlook in interfata: test/diagnostic, alegerea calendarului, disponibilitate, sincronizare, conflicte."""

from __future__ import annotations

from ..i18n import tr

import logging
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

from ..domain.settings import Settings
from ..domain.timeutil import local_day_bounds_utc
from ..errors import FocusDeskError
from ..integrations.calendar import AvailabilityResult
from ..integrations.outlook import CalendarInfo, MailHandoffUncertain, SyncRequest, availability_from_events, execute
from ..services.calendar_sync import CalendarSyncService, PlannedOp, SyncSummary
from ..services.mail import MailDraft, validate_attachments
from ..workers.com_worker import ComBlocked, ComTimeout, ComWorker
from .common import ModalDialog, ask_choice, confirm, error_color, make_tree, ok_color, show_error, show_info
from .planning import fmt_range, sync_state_text

if TYPE_CHECKING:
    from .app import FocusDeskApp

log = logging.getLogger(__name__)
COM_TIMEOUT_S = 40


def _backend_factory():
    from ..integrations.outlook_com import OutlookComBackend

    return OutlookComBackend()


class OutlookController:
    def __init__(self, app: "FocusDeskApp", backend_factory: Callable = _backend_factory, use_com: bool = True) -> None:
        self.app = app
        self.worker = ComWorker(app.bridge, backend_factory, use_com=use_com)
        self.sync_service: CalendarSyncService | None = None
        self.verified = False  # true doar dupa un test reusit in aceasta rulare
        self.last_error: str | None = None
        self._mail_pending = False

    # ---- state ------------------------------------------------------
    def attach(self) -> None:
        ws = self.app.ws
        self.sync_service = CalendarSyncService(ws, self.app.sessions)
        self.verified = False
        n = self.sync_service.recover_interrupted() if not ws.read_only else 0
        if n:
            self.app.status.set_message(tr('ui.outlook_ui.operatii_de_calendar_intrerupte_reincearca_sincronizarea', n=n))
        self.refresh_status()

    @property
    def settings(self):
        return self.app.ws.settings.outlook

    def enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.calendar_store_id and self.settings.calendar_folder_id)

    def refresh_status(self) -> None:
        o = self.settings
        if not o.enabled:
            self.app.status.set_calendar(tr('ui.outlook_ui.calendar_local_outlook_dezactivat'))
        elif not self.enabled():
            self.app.status.set_calendar(tr('ui.outlook_ui.calendar_outlook_neconfigurat'), "muted")
        elif self.verified:
            self.app.status.set_calendar(tr('ui.outlook_ui.calendar_outlook', o_calendar_name_or_ales=o.calendar_name or 'ales'), "ok")
        elif self.last_error:
            self.app.status.set_calendar(tr('ui.outlook_ui.calendar_outlook_indisponibil'), "error")
        else:
            self.app.status.set_calendar(tr('ui.outlook_ui.calendar_outlook_neverificat', o_calendar_name_or_ales=o.calendar_name or 'ales'), "muted")

    def shutdown(self) -> None:
        self.worker.shutdown()

    # ---- errors -----------------------------------------------------
    def _error(self, exc: BaseException) -> str:
        if isinstance(exc, (ComTimeout, ComBlocked)):
            msg = str(exc)
        else:
            msg = f"{type(exc).__name__}: {exc}"
        self.last_error = msg
        self.verified = False
        self.refresh_status()
        return msg

    # ---- test / diagnostic ------------------------------------------
    def test(self, on_ready: Callable[[dict, list[CalendarInfo]], None] | None = None) -> None:
        self.app.status.set_busy(tr('ui.outlook_ui.se_testeaza_outlook'))

        def work(backend):
            diag = backend.diagnose()
            cals = backend.list_calendars() if diag.get("outlook") else []
            return diag, cals

        def done(res) -> None:
            self.app.status.clear_busy()
            diag, cals = res
            if diag.get("outlook"):
                self.verified, self.last_error = True, None
            else:
                self.verified = False
                self.last_error = diag.get("error") or tr('ui.outlook_ui.outlook_indisponibil')
            self.refresh_status()
            if on_ready:
                on_ready(diag, cals)
            else:
                OutlookDiagnosticDialog(self.app.root, self.app, diag, cals).run()

        def failed(exc: BaseException) -> None:
            self.app.status.clear_busy()
            show_error(self.app.root, self._error(exc), tr('ui.outlook_ui.test_outlook'))

        self.worker.submit(work, done, failed, timeout_s=COM_TIMEOUT_S, name="outlook-test")

    # ---- availability -----------------------------------------------
    def get_availability(self, start_day, end_day, on_done: Callable[[AvailabilityResult], None],
                         on_error: Callable[[BaseException], None] | None = None) -> None:
        if not self.enabled():
            on_done(AvailabilityResult())
            return
        o = self.settings
        tz = self.app.ws.settings.timezone
        start = local_day_bounds_utc(start_day, tz)[0]
        end = local_day_bounds_utc(end_day, tz)[1]
        store, folder = o.calendar_store_id, o.calendar_folder_id

        def work(backend):
            return backend.read_events(store, folder, start, end)

        def done(events) -> None:
            self.verified, self.last_error = True, None
            self.refresh_status()
            on_done(availability_from_events(events, o, start, end))

        def failed(exc: BaseException) -> None:
            msg = self._error(exc)
            # Nu pretindem ca am verificat calendarul de serviciu: revenim la disponibilitate locala si spunem asta.
            res = AvailabilityResult(note=tr('ui.outlook_ui.disponibilitate_verificata_doar_local_outlook_indisponibil')
                                          + msg.splitlines()[0][:120] + ")")
            on_done(res)

        self.worker.submit(work, done, failed, timeout_s=COM_TIMEOUT_S, name="outlook-availability")

    def get_calendar_events(self, start_day, end_day, on_done: Callable[[list], None],
                            on_error: Callable[[BaseException], None]) -> None:
        if not self.enabled():
            on_done([])
            return
        o = self.settings
        tz = self.app.ws.settings.timezone
        start = local_day_bounds_utc(start_day, tz)[0]
        end = local_day_bounds_utc(end_day, tz)[1]
        store, folder = o.calendar_store_id, o.calendar_folder_id

        def work(backend):
            return backend.read_calendar_events(store, folder, start, end)

        def done(events) -> None:
            self.verified, self.last_error = True, None
            self.refresh_status()
            on_done(events)

        def failed(exc: BaseException) -> None:
            self._error(exc)
            on_error(exc)

        self.worker.submit(work, done, failed, timeout_s=COM_TIMEOUT_S, name="outlook-calendar-events")

    # ---- sync -------------------------------------------------------
    def sync(self, session_ids: list[str] | None = None, *, quiet: bool = False) -> None:
        svc = self.sync_service
        if svc is None or self.app.ws.read_only:
            return
        if not self.enabled():
            if not quiet:
                show_info(self.app.root, tr('ui.outlook_ui.outlook_nu_este_configurat_alege_calendarul_in_setari_outlook_sau_folo'))
            return
        planned = svc.prepare(session_ids)
        if not planned:
            if not quiet:
                show_info(self.app.root, tr('ui.outlook_ui.nimic_de_sincronizat_sesiunile_marcate_pentru_calendar_sunt_la_zi_sau'))
            return
        self._run(planned, quiet)

    def _run(self, planned: list[PlannedOp], quiet: bool = False) -> None:
        svc = self.sync_service
        assert svc is not None
        requests = [p.request for p in planned]
        self.app.status.set_busy(tr('ui.outlook_ui.se_sincronizeaza_sesiuni_cu_outlook', len_requests=len(requests)))

        def work(backend):
            return [execute(backend, r) for r in requests]

        def done(results) -> None:
            self.app.status.clear_busy()
            summary = SyncSummary()
            for p, res in zip(planned, results):
                svc.apply(p, res, summary)
            self.verified = summary.failed < len(planned)
            self.last_error = None if self.verified else (summary.messages[0] if summary.messages else None)
            self.refresh_status()
            self.app.on_sessions_changed()
            if not quiet or summary.failed or summary.conflicts:
                self._show_summary(summary, len(planned))

        def failed(exc: BaseException) -> None:
            self.app.status.clear_busy()
            msg = self._error(exc)
            svc.fail_all(planned, msg)
            self.app.on_sessions_changed()
            show_error(self.app.root, tr('ui.outlook_ui.sincronizarea_nu_a_reusit_operatiile_au_ramas_vizibile_ca_esuate_si_po', msg=msg), tr('ui.outlook_ui.outlook'))

        self.worker.submit(work, done, failed, timeout_s=COM_TIMEOUT_S + 5 * len(planned), name="outlook-sync")

    def _show_summary(self, s: SyncSummary, total: int) -> None:
        lines = [tr('ui.outlook_ui.create', s_created=s.created), tr('ui.outlook_ui.actualizate', s_updated=s.updated), tr('ui.outlook_ui.anulate', s_cancelled=s.cancelled),
                 tr('ui.outlook_ui.conflicte', s_conflicts=s.conflicts), tr('ui.outlook_ui.esuate', s_failed=s.failed)]
        extra = "\n".join(dict.fromkeys(m for m in s.messages if m))
        ok = s.created + s.updated + s.cancelled
        head = (tr('ui.outlook_ui.din_operatii_salvate_in_outlook_local', ok=ok, total=total) if ok else tr('ui.outlook_ui.nicio_operatie_nu_a_reusit_complet'))
        text = head + "\n" + "  ·  ".join(lines)
        text += (tr('ui.outlook_ui.atentie_salvat_inseamna_salvat_in_outlook_local_sincronizarea_serverul'))
        if extra:
            text += "\n\n" + extra
        if s.failed or s.conflicts:
            show_error(self.app.root, text, tr('ui.outlook_ui.sincronizare_outlook_partial'))
        else:
            show_info(self.app.root, text, tr('ui.outlook_ui.sincronizare_outlook'))

    # ---- mail -------------------------------------------------------
    def send_mail(self, draft: MailDraft, send: bool, on_done: Callable[[str], None],
                  on_error: Callable[[BaseException], None] | None = None) -> None:
        """Trimite (sau doar deschide ca ciorna) prin Outlook. Nu depinde de calendarul ales in Setari."""
        if self._mail_pending:
            if on_error:
                on_error(ComBlocked(tr('ui.outlook_ui.un_e_mail_este_deja_in_curs_asteapta_rezultatul_inainte_de_o_alta_oper')))
            return
        self._mail_pending = True
        # Freeze the editable form before crossing the thread boundary. Only primitives reach COM.
        to, cc, subject, body = list(draft.to), list(draft.cc), draft.subject, draft.body
        paths = [item.path for item in draft.attachments]
        self.app.status.set_busy(tr('ui.outlook_ui.se_trimite_e_mailul') if send else tr('ui.outlook_ui.se_deschide_ciorna_in_outlook'))

        def work(backend):
            selected = validate_attachments(paths)
            return backend.send_mail(to, cc, subject, body, send=send, attachments=[item.path for item in selected])

        def done(result) -> None:
            self._mail_pending = False
            self.app.status.clear_busy()
            if result not in ("submitted", "displayed"):
                failed(MailHandoffUncertain(tr('ui.outlook_ui.outlook_a_intors_un_rezultat_necunoscut', result=result)))
                return
            on_done(result)

        def failed(exc: BaseException) -> None:
            self._mail_pending = False
            self.app.status.clear_busy()
            if on_error:
                on_error(exc)
                return
            msg = str(exc) if isinstance(exc, (ComTimeout, ComBlocked)) else f"{type(exc).__name__}: {exc}"
            if isinstance(exc, (ComTimeout, MailHandoffUncertain)):
                msg += (tr('ui.outlook_ui.rezultatul_este_incert_verifica_ferestrele_deschise_ciorne_de_trimis_s'))
            show_error(self.app.root, tr('ui.outlook_ui.operatia_e_mail_necesita_verificare', msg=msg), "E-mail")

        self.worker.submit(work, done, failed, timeout_s=COM_TIMEOUT_S, name="outlook-mail")

    # ---- conflicts --------------------------------------------------
    def conflicts(self) -> list:
        return [s for s in self.app.ws.repo.sessions.list_all() if s.sync.state == "conflict"]

    def resolve(self, session_id: str, choice: str) -> None:
        svc = self.sync_service
        if svc is None:
            return
        if choice == "detach":
            svc.detach(session_id)
            self.app.on_sessions_changed()
            return
        planned = svc.request_for_conflict(session_id, choice)
        if planned is not None:
            self._run([planned], quiet=True)


class OutlookDiagnosticDialog(ModalDialog):
    """Rezultatul testului + alegerea calendarului de serviciu (Exchange / Microsoft 365)."""

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", diag: dict, cals: list[CalendarInfo]) -> None:
        super().__init__(parent, tr('ui.outlook_ui.test_outlook_si_alegerea_calendarului'), resizable=True, ok_text=tr('ui.outlook_ui.foloseste_calendarul_ales'),
                         cancel_text=tr('ui.outlook_ui.inchide'))
        self.app = app
        self.cals = cals
        self.geometry("760x520")
        b = self.body
        if diag.get("outlook"):
            ttk.Label(b, text=tr('ui.outlook_ui.outlook_classic_raspunde_prin_com'), foreground=ok_color(self),
                      style="Section.TLabel").pack(anchor="w")
            ttk.Label(b, style="Muted.TLabel", text=(
                tr('ui.outlook_ui.versiune_profil_magazine', diag_get_version_or=diag.get('version') or '?', diag_get_profile_or=diag.get('profile') or '?', len_diag_get_stores=len(diag.get('stores', []))))).pack(anchor="w")
        else:
            ttk.Label(b, text=tr('ui.outlook_ui.outlook_nu_este_disponibil_prin_com'), foreground=error_color(self),
                      style="Section.TLabel").pack(anchor="w")
            ttk.Label(b, wraplength=700, text=diag.get("error") or "").pack(anchor="w")
            ttk.Label(b, wraplength=700, text=diag.get("hint") or tr('ui.outlook_ui.new_outlook_nu_suporta_com_foloseste_exportul_ics'),
                      style="Muted.TLabel").pack(anchor="w", pady=4)
            self.ok_btn.state(["disabled"])
        ttk.Label(b, text=tr('ui.outlook_ui.calendare_gasite_alege_calendarul_de_serviciu_microsoft_365_exchange'),
                  style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        self.tv, frame = make_tree(b, [("name", tr('ui.outlook_ui.calendar'), 700)], height=8)
        frame.pack(fill="both", expand=True)
        cur = app.ws.settings.outlook.calendar_folder_id
        for i, c in enumerate(cals):
            self.tv.insert("", "end", iid=str(i), values=(c.label,))
            if c.folder_id == cur:
                self.tv.selection_set(str(i))
        ttk.Label(b, wraplength=700, style="Muted.TLabel", text=(
            tr('ui.outlook_ui.nu_presupune_ca_primul_calendar_sau_un_fisier_pst_local_se_sincronizea'))).pack(anchor="w", pady=(8, 0))

    def validate(self) -> bool:
        sel = self.tv.selection()
        if not sel:
            show_error(self, tr('ui.outlook_ui.alege_un_calendar'))
            return False
        cal = self.cals[int(sel[0])]
        if not cal.is_exchange and not confirm(
                self, tr('ui.outlook_ui.calendarul_ales_nu_este_exchange_microsoft_365_de_ex_fisier_pst_local')):
            return False
        self._cal = cal
        return True

    def collect(self):
        cal = self._cal
        ws = self.app.ws
        new: Settings = ws.settings.model_copy(deep=True)
        new.outlook.enabled = True
        new.outlook.calendar_store_id = cal.store_id
        new.outlook.calendar_folder_id = cal.folder_id
        new.outlook.calendar_name = tr('ui.outlook_ui.calendar_choice', cal_store_name=cal.store_name, cal_name=cal.name)
        ok = self.app.run_write(lambda: ws.update_settings(new))
        if ok:
            self.app.outlook.refresh_status()
        return ok


class ConflictsDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, tr('ui.outlook_ui.conflicte_cu_outlook'), resizable=True, ok_text=tr('ui.outlook_ui.inchide'), cancel_text=tr('ui.outlook_ui.inchide'))
        self.ok_btn.pack_forget()
        self.app = app
        self.geometry("760x420")
        ttk.Label(self.body, wraplength=700, text=(
            tr('ui.outlook_ui.evenimentul_a_fost_mutat_sters_sau_modificat_in_outlook_fata_de_planul'))).pack(anchor="w")
        self.tv, frame = make_tree(self.body, [("task", tr('ui.outlook_ui.task'), 240), ("when", tr('ui.outlook_ui.plan_local'), 170), ("why", tr('ui.outlook_ui.motiv'), 280)],
                                   height=8)
        frame.pack(fill="both", expand=True, pady=6)
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Button(row, text=tr('ui.outlook_ui.preia_din_outlook'), command=lambda: self._do("pull")).pack(side="left", padx=2)
        ttk.Button(row, text=tr('ui.outlook_ui.aplica_planul_local'), command=lambda: self._do("local")).pack(side="left", padx=2)
        ttk.Button(row, text=tr('ui.outlook_ui.detaseaza_de_calendar'), command=lambda: self._do("detach")).pack(side="left", padx=2)
        ttk.Label(self.body, style="Muted.TLabel", wraplength=700, text=(
            tr('ui.outlook_ui.preia_din_outlook_adopta_ora_din_outlook_sau_anuleaza_sesiunea_locala'))
                  ).pack(anchor="w", pady=(6, 0))
        self._load()

    def _load(self) -> None:
        self.tv.delete(*self.tv.get_children())
        tz = self.app.ws.settings.timezone
        for s in self.app.outlook.conflicts():
            n = self.app.ws.nodes.get(s.node_id)
            self.tv.insert("", "end", iid=s.id, values=(n.title if n else "?", fmt_range(s, tz), s.sync.error or ""))

    def _do(self, choice: str) -> None:
        sel = self.tv.selection()
        if not sel:
            return
        sid = sel[0]
        if choice == "local" and not confirm(self, tr('ui.outlook_ui.rescrii_recreezi_evenimentul_din_outlook_cu_planul_local')):
            return
        self.app.outlook.resolve(sid, choice)
        self.after(1500, self._load)


def build_outlook_settings_page(page: ttk.Frame, dlg) -> Callable[[Settings], None]:
    """Pagina „Outlook” din Setari; intoarce functia care copiaza valorile in Settings."""
    app = dlg.app
    o = dlg.s.outlook
    page.columnconfigure(1, weight=1)
    enabled = tk.BooleanVar(value=o.enabled)
    reminder = tk.StringVar(value=str(o.reminder_minutes))
    details = tk.BooleanVar(value=o.include_details)
    tent = tk.StringVar(value=o.tentative_policy)
    away = tk.StringVar(value=o.working_elsewhere_policy)
    category = tk.StringVar(value=o.category or "")
    ttk.Checkbutton(page, text=tr('ui.outlook_ui.foloseste_outlook_classic_com_pentru_disponibilitate_si_rezervari'),
                    variable=enabled).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
    ttk.Label(page, text=tr('ui.outlook_ui.calendar_ales')).grid(row=1, column=0, sticky="w", pady=3)
    ttk.Label(page, text=o.calendar_name or "(niciunul)", wraplength=420).grid(row=1, column=1, sticky="w")
    ttk.Button(page, text=tr('ui.outlook_ui.testeaza_outlook_si_alege_calendarul'),
               command=lambda: app.outlook.test()).grid(row=1, column=2, padx=6)
    ttk.Label(page, text=tr('ui.outlook_ui.memento_minute_inainte')).grid(row=2, column=0, sticky="w", pady=3)
    ttk.Entry(page, textvariable=reminder, width=6).grid(row=2, column=1, sticky="w")
    ttk.Label(page, text=tr('ui.outlook_ui.categorie_outlook_optional')).grid(row=3, column=0, sticky="w", pady=3)
    ttk.Entry(page, textvariable=category, width=24).grid(row=3, column=1, sticky="w")
    ttk.Label(page, text=tr('ui.outlook_ui.evenimente_provizoriu_blocheaza')).grid(row=4, column=0, sticky="w", pady=3)
    ttk.Combobox(page, textvariable=tent, values=["busy", "free"], state="readonly", width=8).grid(row=4, column=1, sticky="w")
    ttk.Label(page, text=tr('ui.outlook_ui.lucrez_din_alta_locatie_blocheaza')).grid(row=5, column=0, sticky="w", pady=3)
    ttk.Combobox(page, textvariable=away, values=["busy", "free"], state="readonly", width=8).grid(row=5, column=1, sticky="w")
    ttk.Checkbutton(page, text=tr('ui.outlook_ui.include_fragment_din_descrierea_task_ului_in_evenimente_poate_expune_d'),
                    variable=details).grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 2))
    ttk.Label(page, style="Muted.TLabel", wraplength=620, justify="left", text=(
        tr('ui.outlook_ui.functionarea_depinde_de_outlook_classic_si_de_politicile_companiei_foc'))).grid(
        row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def collect(s: Settings) -> None:
        live = app.ws.settings.outlook  # calendarul poate fi ales din dialogul de test intre timp
        s.outlook.calendar_store_id = live.calendar_store_id
        s.outlook.calendar_folder_id = live.calendar_folder_id
        s.outlook.calendar_name = live.calendar_name
        s.outlook.enabled = enabled.get()
        s.outlook.reminder_minutes = max(0, int(reminder.get() or 0))
        s.outlook.include_details = details.get()
        s.outlook.tentative_policy = tent.get()  # type: ignore[assignment]
        s.outlook.working_elsewhere_policy = away.get()  # type: ignore[assignment]
        s.outlook.category = category.get().strip() or None

    return collect
