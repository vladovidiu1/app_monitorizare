"""Integrarea Outlook in interfata: test/diagnostic, alegerea calendarului, disponibilitate, sincronizare, conflicte."""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

from ..domain.settings import Settings
from ..domain.timeutil import local_day_bounds_utc
from ..errors import FocusDeskError
from ..integrations.calendar import AvailabilityResult
from ..integrations.outlook import CalendarInfo, SyncRequest, availability_from_events, execute
from ..services.calendar_sync import CalendarSyncService, PlannedOp, SyncSummary
from ..services.mail import MailDraft
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

    # ---- state ------------------------------------------------------
    def attach(self) -> None:
        ws = self.app.ws
        self.sync_service = CalendarSyncService(ws, self.app.sessions)
        self.verified = False
        n = self.sync_service.recover_interrupted() if not ws.read_only else 0
        if n:
            self.app.status.set_message(f"{n} operații de calendar întrerupte; reîncearcă sincronizarea")
        self.refresh_status()

    @property
    def settings(self):
        return self.app.ws.settings.outlook

    def enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.calendar_store_id and self.settings.calendar_folder_id)

    def refresh_status(self) -> None:
        o = self.settings
        if not o.enabled:
            self.app.status.set_calendar("Calendar: local (Outlook dezactivat)")
        elif not self.enabled():
            self.app.status.set_calendar("Calendar: Outlook neconfigurat", "muted")
        elif self.verified:
            self.app.status.set_calendar(f"Calendar: Outlook — {o.calendar_name or 'ales'}", "ok")
        elif self.last_error:
            self.app.status.set_calendar("Calendar: Outlook indisponibil", "error")
        else:
            self.app.status.set_calendar(f"Calendar: Outlook — {o.calendar_name or 'ales'} (neverificat)", "muted")

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
        self.app.status.set_busy("Se testează Outlook…")

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
                self.last_error = diag.get("error") or "Outlook indisponibil"
            self.refresh_status()
            if on_ready:
                on_ready(diag, cals)
            else:
                OutlookDiagnosticDialog(self.app.root, self.app, diag, cals).run()

        def failed(exc: BaseException) -> None:
            self.app.status.clear_busy()
            show_error(self.app.root, self._error(exc), "Test Outlook")

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
            res = AvailabilityResult(note="Disponibilitate verificată doar local (Outlook indisponibil: "
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
                show_info(self.app.root, "Outlook nu este configurat. Alege calendarul în Setări › Outlook "
                                         "(sau folosește exportul .ics).")
            return
        planned = svc.prepare(session_ids)
        if not planned:
            if not quiet:
                show_info(self.app.root, "Nimic de sincronizat. Sesiunile marcate pentru calendar sunt la zi sau "
                                         "au conflicte de rezolvat.")
            return
        self._run(planned, quiet)

    def _run(self, planned: list[PlannedOp], quiet: bool = False) -> None:
        svc = self.sync_service
        assert svc is not None
        requests = [p.request for p in planned]
        self.app.status.set_busy(f"Se sincronizează {len(requests)} sesiuni cu Outlook…")

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
            show_error(self.app.root, f"Sincronizarea nu a reușit:\n{msg}\n\nOperațiile au rămas vizibile ca eșuate "
                                      "și pot fi reîncercate fără a crea duplicate.", "Outlook")

        self.worker.submit(work, done, failed, timeout_s=COM_TIMEOUT_S + 5 * len(planned), name="outlook-sync")

    def _show_summary(self, s: SyncSummary, total: int) -> None:
        lines = [f"Create: {s.created}", f"Actualizate: {s.updated}", f"Anulate: {s.cancelled}",
                 f"Conflicte: {s.conflicts}", f"Eșuate: {s.failed}"]
        extra = "\n".join(dict.fromkeys(m for m in s.messages if m))
        ok = s.created + s.updated + s.cancelled
        head = (f"{ok} din {total} operații salvate în Outlook (local)." if ok else "Nicio operație nu a reușit complet.")
        text = head + "\n" + "  ·  ".join(lines)
        text += ("\n\nAtenție: „Salvat” înseamnă salvat în Outlook local; sincronizarea serverului Exchange și "
                 "apariția în Teams nu sunt confirmate de FocusDesk.")
        if extra:
            text += "\n\n" + extra
        if s.failed or s.conflicts:
            show_error(self.app.root, text, "Sincronizare Outlook (parțial)")
        else:
            show_info(self.app.root, text, "Sincronizare Outlook")

    # ---- mail -------------------------------------------------------
    def send_mail(self, draft: MailDraft, send: bool, on_done: Callable[[str], None]) -> None:
        """Trimite (sau doar deschide ca ciorna) prin Outlook. Nu depinde de calendarul ales in Setari."""
        self.app.status.set_busy("Se trimite e-mailul…" if send else "Se deschide ciorna în Outlook…")

        def work(backend):
            return backend.send_mail(draft.to, draft.cc, draft.subject, draft.body, send=send)

        def done(result) -> None:
            self.app.status.clear_busy()
            on_done(str(result))

        def failed(exc: BaseException) -> None:
            self.app.status.clear_busy()
            msg = str(exc) if isinstance(exc, (ComTimeout, ComBlocked)) else f"{type(exc).__name__}: {exc}"
            if send and isinstance(exc, ComTimeout):
                msg += ("\n\nNu pot confirma dacă e-mailul a fost trimis. Verifică „Elemente trimise” în Outlook "
                        "înainte să îl retrimiți.")
            show_error(self.app.root, f"E-mailul nu a fost {'trimis' if send else 'deschis'}:\n{msg}", "E-mail")

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
        super().__init__(parent, "Test Outlook și alegerea calendarului", resizable=True, ok_text="Folosește calendarul ales",
                         cancel_text="Închide")
        self.app = app
        self.cals = cals
        self.geometry("760x520")
        b = self.body
        if diag.get("outlook"):
            ttk.Label(b, text="Outlook Classic răspunde prin COM.", foreground=ok_color(self),
                      style="Section.TLabel").pack(anchor="w")
            ttk.Label(b, style="Muted.TLabel", text=(
                f"Versiune: {diag.get('version') or '?'}  ·  Profil: {diag.get('profile') or '?'}  ·  "
                f"Magazine: {len(diag.get('stores', []))}")).pack(anchor="w")
        else:
            ttk.Label(b, text="Outlook nu este disponibil prin COM.", foreground=error_color(self),
                      style="Section.TLabel").pack(anchor="w")
            ttk.Label(b, wraplength=700, text=diag.get("error") or "").pack(anchor="w")
            ttk.Label(b, wraplength=700, text=diag.get("hint") or "New Outlook nu suportă COM; folosește exportul .ics.",
                      style="Muted.TLabel").pack(anchor="w", pady=4)
            self.ok_btn.state(["disabled"])
        ttk.Label(b, text="Calendare găsite (alege calendarul de serviciu Microsoft 365 / Exchange):",
                  style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        self.tv, frame = make_tree(b, [("name", "Calendar", 700)], height=8)
        frame.pack(fill="both", expand=True)
        cur = app.ws.settings.outlook.calendar_folder_id
        for i, c in enumerate(cals):
            self.tv.insert("", "end", iid=str(i), values=(c.label,))
            if c.folder_id == cur:
                self.tv.selection_set(str(i))
        ttk.Label(b, wraplength=700, style="Muted.TLabel", text=(
            "Nu presupune că primul calendar sau un fișier PST local se sincronizează cu Exchange/Teams. "
            "Evenimentele create sunt personale (fără participanți, fără link Teams), cu starea „Ocupat”. "
            "Pentru evenimentele din calendar nu se trimite nimic: doar Save().")).pack(anchor="w", pady=(8, 0))

    def validate(self) -> bool:
        sel = self.tv.selection()
        if not sel:
            show_error(self, "Alege un calendar.")
            return False
        cal = self.cals[int(sel[0])]
        if not cal.is_exchange and not confirm(
                self, "Calendarul ales NU este Exchange/Microsoft 365 (de ex. fișier PST local). Evenimentele nu vor "
                      "apărea în Teams sau pe alte dispozitive. Îl folosesc oricum?"):
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
        new.outlook.calendar_name = f"{cal.store_name} › {cal.name}"
        ok = self.app.run_write(lambda: ws.update_settings(new))
        if ok:
            self.app.outlook.refresh_status()
        return ok


class ConflictsDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, "Conflicte cu Outlook", resizable=True, ok_text="Închide", cancel_text="Închide")
        self.ok_btn.pack_forget()
        self.app = app
        self.geometry("760x420")
        ttk.Label(self.body, wraplength=700, text=(
            "Evenimentul a fost mutat, șters sau modificat în Outlook față de planul local. Nimic nu se rescrie "
            "automat. Alege:")).pack(anchor="w")
        self.tv, frame = make_tree(self.body, [("task", "Task", 240), ("when", "Plan local", 170), ("why", "Motiv", 280)],
                                   height=8)
        frame.pack(fill="both", expand=True, pady=6)
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Button(row, text="Preia din Outlook", command=lambda: self._do("pull")).pack(side="left", padx=2)
        ttk.Button(row, text="Aplică planul local", command=lambda: self._do("local")).pack(side="left", padx=2)
        ttk.Button(row, text="Detașează de calendar", command=lambda: self._do("detach")).pack(side="left", padx=2)
        ttk.Label(self.body, style="Muted.TLabel", wraplength=700, text=(
            "„Preia din Outlook” adoptă ora din Outlook (sau anulează sesiunea locală dacă evenimentul a fost șters). "
            "„Aplică planul local” rescrie/recreează evenimentul. „Detașează” oprește sincronizarea acestei sesiuni.")
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
        if choice == "local" and not confirm(self, "Rescrii/recreezi evenimentul din Outlook cu planul local?"):
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
    ttk.Checkbutton(page, text="Folosește Outlook Classic (COM) pentru disponibilitate și rezervări",
                    variable=enabled).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
    ttk.Label(page, text="Calendar ales").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Label(page, text=o.calendar_name or "(niciunul)", wraplength=420).grid(row=1, column=1, sticky="w")
    ttk.Button(page, text="Testează Outlook și alege calendarul…",
               command=lambda: app.outlook.test()).grid(row=1, column=2, padx=6)
    ttk.Label(page, text="Memento (minute înainte)").grid(row=2, column=0, sticky="w", pady=3)
    ttk.Entry(page, textvariable=reminder, width=6).grid(row=2, column=1, sticky="w")
    ttk.Label(page, text="Categorie Outlook (opțional)").grid(row=3, column=0, sticky="w", pady=3)
    ttk.Entry(page, textvariable=category, width=24).grid(row=3, column=1, sticky="w")
    ttk.Label(page, text="Evenimente „Provizoriu” blochează?").grid(row=4, column=0, sticky="w", pady=3)
    ttk.Combobox(page, textvariable=tent, values=["busy", "free"], state="readonly", width=8).grid(row=4, column=1, sticky="w")
    ttk.Label(page, text="„Lucrez din altă locație” blochează?").grid(row=5, column=0, sticky="w", pady=3)
    ttk.Combobox(page, textvariable=away, values=["busy", "free"], state="readonly", width=8).grid(row=5, column=1, sticky="w")
    ttk.Checkbutton(page, text="Include fragment din descrierea task-ului în evenimente (poate expune date sensibile)",
                    variable=details).grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 2))
    ttk.Label(page, style="Muted.TLabel", wraplength=620, justify="left", text=(
        "Funcționarea depinde de Outlook Classic și de politicile companiei; FocusDesk nu încearcă să le ocolească. "
        "New Outlook nu suportă COM — folosește exportul .ics. Descrierea evenimentului nu conține căi locale. "
        "„Salvat” = salvat în Outlook local; sincronizarea Exchange/Teams nu este confirmată de aplicație.")).grid(
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
