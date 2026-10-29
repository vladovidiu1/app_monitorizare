"""Fereastra principala FocusDesk."""

from __future__ import annotations

from ..i18n import tr

import logging
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

import ttkbootstrap as tb

from .. import __version__
from ..config import AppConfig, resource_path
from ..domain.common import utcnow
from ..domain.labels import format_seconds
from ..domain.models import CLOSED_STATUSES, Kind, Node, Status
from ..errors import (
    ExternalModificationError, FocusDeskError, ReadOnlyError, WorkspaceLockedError,
)
from ..services import backup as backup_service
from ..services.checkpoints import CheckpointService
from ..services.files import FileService
from ..services.mail import journal_text
from ..services.planning import PlanningService
from ..services.queries import Queries
from ..services.recurrence import RecurrenceService
from ..services.scheduler import CheckpointScheduler
from ..services.sessions import SessionService, session_signature
from ..services.timer import TimerService
from ..services.workspace import Workspace
from ..integrations import system as system_open
from ..integrations.calendar import AvailabilityResult, LocalOnlyProvider
from ..integrations.ics import IcsExportProvider, IcsItem, stable_uid
from ..workers.bridge import Job, UiBridge
from .calendar_page import PlanTab
from .meetings import CalendarHub as CalendarPage
from .common import (
    ModalDialog, THEMES, SessionButton, ask_choice, ask_string, apply_theme, confirm, show_error, show_info,
)
from .dashboard import DashboardWindow
from .dialogs import IssuesDialog, MoveDialog, NewNodeDialog, NodePickerDialog, TrashDialog
from .inspector import Inspector
from .mail_ui import DescriptionSourceDialog, MailDialog
from .outlook_ui import ConflictsDialog, OutlookController
from .planning import ManualSessionDialog, MissedRecurrenceDialog, PlannerDialog, RecurrenceDialog
from .sidebar import Sidebar
from .statusbar import StatusBar
from .tab_details import DetailsTab
from .tab_files import FilesTab
from .tab_journal import JournalTab
from .tab_subtasks import SubtasksTab
from .tab_versions import VersionsTab
from .tasklist import TaskList
from .today import TodayPage
from .activity_page import ActivityPage
from .task_space import TaskSpace
from .user_guide import GuideController

log = logging.getLogger(__name__)

VIEW_TITLES = {"today":tr('ui.app.astazi'), "tasks":tr('ui.app.proiecte_si_taskuri'), "calendar":tr('ui.outlook_ui.calendar'), "activity":tr('ui.activity_page.activitate'), "archive":tr('ui.app.arhiva')}
VIEW_HINTS = {"tasks":tr('ui.app.niciun_task_adauga_un_task_sau_schimba_filtrele'), "archive":tr('ui.app.arhiva_este_goala')}


class FocusDeskApp:
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.config = AppConfig.load()
        self.config.theme = theme = "light"
        self.root = tb.Window(title="FocusDesk", theme=THEMES[theme], size=(1440, 900), minsize=(1100, 700))
        self._set_icon()
        apply_theme(self.root, theme)
        from .design import px, MIN_WINDOW
        self.root.minsize(*(px(self.root,v) for v in MIN_WINDOW))
        if self.config.geometry:
            try:
                self.root.geometry(self.config.geometry)
            except tk.TclError:
                pass
        self.bridge = UiBridge(self.root)
        from ..services.gmail import GmailService
        self.gmail = GmailService(self.config,self.bridge)
        self.outlook = OutlookController(self)
        self.ws: Workspace | None = None  # type: ignore[assignment]
        self.q: Queries | None = None  # type: ignore[assignment]
        self.timer: TimerService | None = None
        self.files: FileService = None  # type: ignore[assignment]
        self.checkpoints: CheckpointService = None  # type: ignore[assignment]
        self.sessions: SessionService = None  # type: ignore[assignment]
        self.planning: PlanningService = None  # type: ignore[assignment]
        self.recurrence: RecurrenceService = None  # type: ignore[assignment]
        self.scheduler: CheckpointScheduler | None = None
        self._sched_running = False
        self._tick_count = 0
        self.session_buttons: list[SessionButton] = []
        self.dashboard: DashboardWindow | None = None
        self.followup_dialog = None
        self.mail_dialog = None
        self._mail_composing = False
        self.calendar_provider = LocalOnlyProvider()
        self._busy = 0
        self.current_view = "today"
        self.current_scope: str | None = None
        self.selected_id: str | None = None
        self._refresh_pending = False
        self._workspace_jobs=[]
        self._search_job = None
        self._gap_dialog_open = False
        self._tick_job = None
        self._layout_generation = 0
        self._initial_path = workspace_path
        self.user_guide = GuideController(self)
        self._build_menu()
        self._build_layout()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ================================================================
    # UI construction
    # ================================================================
    def _set_icon(self) -> None:
        try:
            ico = resource_path("focusdesk.ico")
            if ico.exists():
                self.root.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, padding=(16, 12, 16, 10))
        top.pack(fill="x")
        from .design import icon
        ttk.Label(top, text="  FocusDesk", image=icon(top,"brand",24), compound="left", style="Brand.TLabel").pack(side="left")
        self.guide_btn = ttk.Button(top, text=tr('ui.app.ghid_de_utilizare'), image=icon(top,"help",20), compound="left",
                                    style="Quiet.TButton", command=self.show_guide, takefocus=True)
        self.guide_btn.pack(side="left", padx=(10, 0))
        from .common import Tooltip
        Tooltip(self.guide_btn, tr('ui.app.ghid_local_de_utilizare_f1_pentru_ajutor_contextual'))
        self.ws_label = ttk.Label(top, text="", style="Muted.TLabel", width=21)
        self.ws_label.pack(side="left", padx=(12, 0), pady=(3, 0))
        self.new_btn = tb.Menubutton(top, text=tr('common.new'), bootstyle="primary")
        self.new_menu = tk.Menu(self.new_btn, tearoff=False)
        self.new_menu.add_command(label=tr('ui.app.din_sablon'), command=self.new_from_template)
        self.new_menu.add_command(label=tr('common.task_shortcut'), command=lambda: self.new_node(Kind.TASK))
        self.new_menu.add_command(label=tr('ui.app.subtask_in_selectia_curenta'), command=self.new_subtask)
        self.new_menu.add_separator()
        self.new_menu.add_command(label=tr('ui.app.folder_categorie'), command=lambda: self.new_node(Kind.FOLDER))
        self.new_menu.add_command(label=tr('ui.app.proiect'), command=lambda: self.new_node(Kind.PROJECT))
        self.new_btn["menu"] = self.new_menu
        self.new_btn.pack(side="right")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=34)
        self.search_entry.pack(side="right", fill="x", expand=True, padx=(0, 16))
        ttk.Label(top, text="", image=icon(top,"search"), style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self.search_var.trace_add("write", lambda *_: self._debounce_search())
        self.search_entry.bind("<Escape>", lambda _e: self._clear_search())
        self.search_entry.bind("<Return>", lambda _e: self._run_search())

        self.status = StatusBar(self.root)
        self.status.pack(side="bottom", fill="x")
        ttk.Separator(self.root).pack(side="bottom", fill="x")

        from .session_ui import TimerIndicator
        self.status._labels['timer'].pack_forget()
        self.status._labels['workspace'].configure(width=18)
        self.timer_indicator=TimerIndicator(self.status,self)
        self.timer_indicator.pack(side='left',fill='x',expand=True)
        self.paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self.sidebar = Sidebar(self.paned, self)
        self.center = ttk.Frame(self.paned)
        self.inspector = Inspector(self.paned, self)
        self.paned.add(self.sidebar, weight=0)
        self.paned.add(self.center, weight=1)
        self.paned.add(self.inspector, weight=0)
        self.sidebar.configure(width=230)
        self.inspector.configure(width=470)
        self.tasklist = TaskList(self.center, self)
        self.today = TodayPage(self.center, self)
        self.calendar_page = CalendarPage(self.center, self)
        self.activity_page = ActivityPage(self.center, self)
        self.inspector.add_tab(DetailsTab(self.inspector.nb, self))
        self.inspector.add_tab(SubtasksTab(self.inspector.nb, self))
        self.inspector.add_tab(JournalTab(self.inspector.nb, self))
        self.inspector.add_tab(FilesTab(self.inspector.nb, self))
        self.inspector.add_tab(PlanTab(self.inspector.nb, self))
        self.inspector.add_tab(VersionsTab(self.inspector.nb, self))
        self.task_space = TaskSpace(self.center,self)
        self._schedule_sashes(80)

    def _schedule_sashes(self, delay=0):
        generation = self._layout_generation
        callback = lambda: self._apply_sashes(generation=generation)
        if delay: self.root.after(delay,callback)
        else: self.root.after_idle(callback)

    def _apply_sashes(self, attempt: int = 0, generation=None) -> None:
        if generation is None: generation = self._layout_generation
        if generation != self._layout_generation: return
        try:
            self.root.update_idletasks()
            total = self.paned.winfo_width()
            if total < 600 and attempt < 10:
                self.root.after(100, lambda: self._apply_sashes(attempt + 1,generation))
                return
            panes = self.paned.panes()
            from .design import px
            left = self.config.sash_left or px(self.root,210)
            right = self.config.sash_right or px(self.root,400)
            right = max(px(self.root,380), min(right, total - left - px(self.root,400)))  # lista din mijloc ramane suficient de lata
            has_inspector = str(self.inspector) in panes
            self.paned.sashpos(0, left)
            if has_inspector:
                self.paned.sashpos(1, max(left + px(self.root,400), total - right))
        except tk.TclError:
            pass

    def _build_menu(self) -> None:
        m = tk.Menu(self.root)
        self.root.configure(menu=m)
        self.menubar = m
        # Fisier
        f = tk.Menu(m, tearoff=False)
        m.add_cascade(label=tr('ui.tab_versions.fisier'), menu=f, underline=0)
        f.add_command(label=tr('ui.app.deschide_workspace'), command=self.menu_open_workspace)
        f.add_command(label=tr('ui.app.workspace_nou'), command=self.menu_new_workspace)
        f.add_command(label=tr('ui.app.creeaza_workspace_demonstrativ'), command=self.menu_demo_workspace)
        self.recent_menu = tk.Menu(f, tearoff=False)
        f.add_cascade(label=tr('menu.recent_workspaces'), menu=self.recent_menu)
        f.add_separator()
        f.add_command(label=tr('ui.app.salveaza_ctrl_s'), command=self.save_current)
        f.add_command(label=tr('ui.app.rescaneaza_workspace'), command=self.rescan)
        f.add_separator()
        f.add_command(label=tr('ui.app.backup_acum_metadate'), command=lambda: self.backup_now(False))
        f.add_command(label=tr('ui.app.backup_acum_complet_cu_fisiere'), command=lambda: self.backup_now(True))
        f.add_command(label=tr('ui.app.restaureaza_backup_intr_un_folder_nou'), command=self.restore_backup)
        f.add_separator()
        f.add_command(label=tr('ui.app.cos'), command=self.open_trash)
        f.add_separator()
        f.add_command(label=tr('ui.app.iesire'), command=self.on_close)
        self.file_menu = f
        # Organizare
        o = tk.Menu(m, tearoff=False)
        m.add_cascade(label=tr('ui.app.organizare'), menu=o, underline=0)
        o.add_command(label=tr('ui.app.task_nou_ctrl_n'), command=lambda: self.new_node(Kind.TASK))
        o.add_command(label=tr('ui.app.subtask_nou'), command=self.new_subtask)
        o.add_command(label=tr('ui.app.folder_nou'), command=lambda: self.new_node(Kind.FOLDER))
        o.add_command(label=tr('ui.app.proiect_nou'), command=lambda: self.new_node(Kind.PROJECT))
        o.add_separator()
        o.add_command(label=tr('ui.app.redenumeste_f2'), command=self.rename_selected)
        o.add_command(label=tr('ui.app.muta'), command=self.move_selected)
        o.add_command(label=tr('ui.app.face_subtask_al_task_ului_de_deasupra_alt'), command=self.indent_selected)
        o.add_command(label=tr('ui.app.scoate_un_nivel_alt'), command=self.outdent_selected)
        o.add_command(label=tr('ui.app.adauga_legatura'), command=self.link_selected)
        o.add_command(label=tr('ui.app.prioritate_pentru_azi_comuta'), command=self.toggle_pin_selected)
        o.add_command(label=tr('ui.tab_subtasks.finalizeaza_redeschide'), command=self.toggle_done_selected)
        o.add_separator()
        o.add_command(label=tr('ui.app.arhiveaza_dezarhiveaza'), command=self.toggle_archive_selected)
        o.add_command(label=tr('ui.app.trimite_in_cos'), command=self.trash_selected)
        o.add_separator()
        o.add_command(label=tr('ui.app.programeaza_sesiune'), command=lambda: self.schedule_session())
        o.add_command(label=tr('ui.app.planificare_asistata'), command=self.open_planner)
        o.add_command(label=tr('menu.recurring_tasks'), command=self.open_recurrences)
        o.add_command(label=tr('ui.app.trimite_e_mail_din_task_ctrl_m'), command=self.compose_mail)
        o.add_separator()
        self.session_menu = tk.Menu(o, tearoff=False)
        self.session_menu.add_command(label=tr('ui.app.incepe_sesiune_pentru_selectie'), command=self.start_selected_session)
        self.session_menu.add_command(label=tr('ui.app.pauza_continua'), command=self.toggle_pause)
        self.session_menu.add_command(label=tr('ui.app.opreste_sesiunea_2'), command=self.stop_session)
        o.add_cascade(label=tr('ui.app.sesiune_de_lucru'), menu=self.session_menu)
        self.org_menu = o
        # Instrumente
        t = tk.Menu(m, tearoff=False)
        m.add_cascade(label=tr('ui.app.instrumente'), menu=t, underline=0)
        self.dark_var = tk.BooleanVar(value=self.config.theme == "dark")
        t.add_command(label=tr('ui.app.aspect_luminos_focusdesk'), command=self.toggle_theme)
        self.inspector_var = tk.BooleanVar(value=self.config.show_inspector)
        t.add_checkbutton(label=tr('ui.app.arata_inspectorul'), variable=self.inspector_var, command=self.toggle_inspector)
        self.archived_var = tk.BooleanVar(value=self.config.show_archived)
        t.add_checkbutton(label=tr('ui.app.arata_elementele_arhivate_in_arbore'), variable=self.archived_var,
                          command=self.toggle_archived)
        self.completed_var = tk.BooleanVar(value=self.config.show_completed)
        t.add_checkbutton(label=tr('ui.app.arata_taskurile_inchise_in_arbore'), variable=self.completed_var,
                          command=self.toggle_completed)
        t.add_separator()
        t.add_command(label=tr('ui.app.calendar_lunar_de_activitate_ctrl_d'), command=self.open_dashboard)
        t.add_separator()
        t.add_command(label=tr('ui.app.verificare_integritate_workspace'), command=self.show_issues)
        t.add_command(label=tr('ui.app.gestionare_sabloane'), command=self.manage_templates)
        t.add_command(label=tr('ui.app.setari'), command=self.open_settings)
        self.tools_menu = t
        # Ajutor
        h = tk.Menu(m, tearoff=False)
        m.add_cascade(label=tr('ui.app.ajutor'), menu=h, underline=0)
        h.add_command(label=tr('ui.app.ghid_de_utilizare'), command=self.show_guide)
        h.add_command(label=tr('ui.app.ajutor_contextual_f1'), command=lambda:self.show_guide(contextual=True))
        h.add_command(label=tr('ui.app.scurtaturi_de_tastatura'), command=self.show_shortcuts)
        h.add_command(label=tr('ui.app.despre_focusdesk'), command=self.show_about)
        self.help_menu = h

    def _bind_keys(self) -> None:
        r = self.root
        r.bind_all("<F1>", lambda _e: (self.show_guide(contextual=True), "break")[1])
        r.bind("<F11>",self.toggle_task_focus)
        r.bind("<Control-n>", lambda _e: self.new_node(Kind.TASK))
        r.bind("<Control-f>", lambda _e: (self.search_entry.focus_set(), self.search_entry.select_range(0, "end")))
        r.bind("<Control-s>", lambda _e: self.save_current())
        r.bind("<F2>", lambda _e: self.rename_selected())
        r.bind("<F5>", lambda _e: self.reload_preserving_context())
        r.bind("<Control-m>", lambda _e: self.compose_mail())
        r.bind("<Control-d>", lambda _e: self.open_dashboard())
        r.bind("<Alt-Right>", lambda _e: self.indent_selected())
        r.bind("<Alt-Left>", lambda _e: self.outdent_selected())

    # ================================================================
    # Lifecycle
    # ================================================================
    def run(self) -> None:
        self.root.after(50, self._startup)
        self.root.mainloop()

    def _startup(self) -> None:
        path = self._initial_path or (Path(self.config.last_workspace) if self.config.last_workspace else None)
        if path is not None and (path / "workspace.json").is_file():
            if self.open_workspace(path):
                return
        self.welcome()

    def welcome(self) -> None:
        choice = ask_choice(self.root, tr('ui.app.bun_venit_in_focusdesk'),
                            tr('ui.app.alege_unde_tii_datele_workspace_ul_este_un_folder_local_json_markdown'),
                            [("new", tr('ui.app.workspace_nou')), ("open", tr('ui.app.deschide_existent')),
                             ("demo", tr('ui.app.workspace_demonstrativ')), ("quit", tr('ui.app.iesire'))])
        if choice == "new":
            if not self.menu_new_workspace():
                self.welcome()
        elif choice == "open":
            if not self.menu_open_workspace():
                self.welcome()
        elif choice == "demo":
            if not self.menu_demo_workspace():
                self.welcome()
        else:
            self.root.destroy()

    def open_workspace(self, path: Path, *, create: bool = False, name: str = "FocusDesk") -> bool:
        if not self._release_current():
            return False
        try:
            ws = Workspace.open(path, create=create, name=name)
        except FocusDeskError as exc:
            show_error(self.root, str(exc))
            return False
        except Exception as exc:
            log.exception("Deschiderea workspace-ului a esuat")
            show_error(self.root, tr('ui.app.workspace_ul_nu_a_putut_fi_deschis', exc=exc))
            return False
        if ws.repo.lock_conflict:
            ans = ask_choice(self.root, tr('ui.app.workspace_deja_deschis'),
                             tr('ui.app.workspace_ul_este_deschis_intr_o_alta_instanta_focusdesk_poti_continua'),
                             [("ro", tr('ui.app.deschide_doar_pentru_citire')), ("cancel", tr('ui.planning.renunta'))])
            if ans != "ro":
                ws.close()
                return False
        self._attach(ws, path)
        return True

    def _attach(self, ws: Workspace, path: Path) -> None:
        self.ws = ws
        self.q = Queries(ws)
        self.tasklist._source = lambda: self.q.tasks()
        self.tasklist.scope_id = None
        self.tasklist._source_key = None
        self.timer = TimerService(ws)
        self.files = FileService(ws)
        self.checkpoints = CheckpointService(ws)
        self.sessions = SessionService(ws)
        self.planning = PlanningService(ws, self.sessions)
        self.recurrence = RecurrenceService(ws)
        self.scheduler = CheckpointScheduler(ws)
        ws.subscribe(self._on_ws_event)
        self.config.remember_workspace(path)
        self.config.save()
        self.root.title(tr('ui.settings_dialog.focusdesk', ws_name=ws.name) + (tr('common.readonly_suffix') if ws.read_only else ""))
        self.ws_label.configure(text=ws.name)
        self.status.set_workspace(ws.name, str(path), ws.read_only)
        self.status.set_saved() if not ws.read_only else self.status.set_save_idle(tr('ui.meetings.doar_citire'))
        self.status.set_calendar(tr('ui.app.calendar_local'))
        self._rebuild_recent_menu()
        self.outlook.attach()
        self.sidebar._first_fill = True
        self.selected_id = None
        self.show_view(self.config.last_view, select_sidebar=True)
        self.sidebar.refresh()
        self.root.after(200, self._post_open_checks)
        self._tick()

    def _post_open_checks(self) -> None:
        ws = self.ws
        if ws is None:
            return
        errors = [i for i in ws.issues if i.severity == "error"]
        if ws.recovery_messages or errors:
            IssuesDialog(self.root, ws).run()
        if self.timer and self.timer.recovered and not ws.read_only:
            self._handle_recovered_timer()
        if self.timer and self.timer.recovery_error:
            show_info(self.root,self.timer.recovery_error+tr('ui.app.nu_pornesc_alt_timer_peste_acest_fisier_verifica_datele_sau_backupul'))
        diagnostic=self.sessions.diagnostics(self.timer.state.session_id if self.timer and self.timer.state else None)
        if diagnostic['orphan_active'] or diagnostic['overlapping_work']:
            show_info(self.root, tr('ui.app.diagnostic_sesiuni_inregistrari_active_fara_timer_curent_suprapuneri_d', len_diagnostic_orphan_active=len(diagnostic['orphan_active']), len_diagnostic_overlapping_work=len(diagnostic['overlapping_work'])))
        if not ws.read_only:
            self._maintenance_on_open()
            self.root.after(3000, lambda: self.check_scheduled_checkpoints(startup=True))
        if not ws.read_only and ws.settings.backup.daily:
            self._track_workspace_job(self.bridge.submit(lambda tok: backup_service.ensure_daily_backup(ws),
                               on_done=lambda r: self.status.set_message(
                                   tr('ui.app.backup_zilnic_creat', r_kind=r.kind) if r else ""),
                               on_error=lambda e: self.status.set_message(tr('ui.app.backup_zilnic_esuat', e=e)),
                               name="daily-backup"))

    def _maintenance_on_open(self) -> None:
        """Sesiuni ratate, instante recurente de azi si zilele ratate (de ales de utilizator)."""
        ws = self.ws
        missed_sessions = 0
        try:
            missed_sessions = self.sessions.mark_missed()
            created, missed = self.recurrence.generate_today_all()
        except FocusDeskError as exc:
            self.status.set_message(tr('ui.app.intretinere_la_pornire', exc=exc))
            return
        msgs = []
        if missed_sessions:
            msgs.append(tr('ui.app.sesiuni_planificate_au_fost_marcate_ca_ratate', missed_sessions=missed_sessions))
        if created:
            msgs.append(tr('ui.app.task_uri_recurente_create_pentru_azi', len_created=len(created)))
        if msgs:
            self.status.set_message("; ".join(msgs))
        if created or missed_sessions:
            self.refresh_all()
        if missed:
            MissedRecurrenceDialog(self.root, self, missed).run()
            self.refresh_all()

    def _release_current(self) -> bool:
        if self.ws is None:
            return True
        if self._pending_workspace_jobs():return False
        if not self.confirm_leave():
            return False
        if self.timer and self.timer.recovered and not self.ws.read_only:
            self._handle_recovered_timer()
            if self.timer.recovered:return False
        if self.timer and self.timer.active and not self.ws.read_only:
            ans = ask_choice(self.root, tr('ui.app.sesiune_activa'),
                             tr('ui.app.este_o_sesiune_de_lucru_activa_ce_faci_cu_ea_inainte_de_a_schimba_work'),
                             [("stop", tr('ui.app.opreste_sesiunea')), ("keep", tr('ui.app.salveaza_in_pauza_pentru_recuperare_la_redeschidere')),
                              ("cancel", tr('ui.meetings.anuleaza'))])
            if ans == "stop":
                if not self.stop_session():
                    return False
            elif ans == 'keep':
                if not self.run_write(self.timer.pause):return False
            else:
                return False
        # Stopping a coded task can enqueue its automatic checkpoint.
        if self._pending_workspace_jobs():return False
        for tab in [*self.inspector.tabs, *self.task_space.sections.values()]:
            if isinstance(tab, FilesTab): tab.detach_workspace()
        self.calendar_page.meetings.cancel_import()
        self.task_space.leave_route()
        self.task_space.positions.clear()
        self.inspector.node_id = None
        for tab in self.inspector.tabs: tab.node_id = None
        self.inspector.tab_by_id("details").desc.edit_reset()
        self.ws.close()
        self.ws = None  # type: ignore[assignment]
        self.q = None  # type: ignore[assignment]
        self.timer = None
        self.calendar_page.meetings.workspace=None
        self.calendar_page.meetings.mid=None
        self.timer_indicator.update_state()
        return True

    def on_close(self) -> None:
        if self.gmail.busy:
            self.status.set_message(tr('gmail.error.busy'))
            return
        if self.ws is not None and not self._release_current():
            return
        try:
            self.config.geometry = self.root.geometry()
            if self.paned.winfo_width() > 10:
                self.config.sash_left = self.paned.sashpos(0)
                self.config.sash_right = self.paned.winfo_width() - self.paned.sashpos(1)
        except tk.TclError:
            pass
        self.config.save()
        self.outlook.shutdown()
        self.gmail.clear_session()
        self.bridge.close()
        for pending in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", pending)
        self.root.destroy()

    # ================================================================
    # Events / refresh
    # ================================================================
    def _on_ws_event(self, event: str, data: dict) -> None:
        if event in ("node_created", "node_updated", "node_moved", "node_trashed", "node_restored", "reloaded",
                     "sessions_changed", "trash_changed", "notes_changed", "timer_changed", "session_finished", "settings_changed"):
            self._schedule_refresh(event, data)
        elif event in ('meetings_changed','meeting_notes_changed'):
            if self.current_view=='calendar':self.calendar_page.meetings.refresh()
        elif event == "timer_gap":
            self.root.after(0, self._handle_timer_gap)

    def _schedule_refresh(self, event="reloaded", data=None) -> None:
        if not hasattr(self,"_pending_events"): self._pending_events = []
        self._pending_events.append((event,data or {}))
        if not self._refresh_pending:
            self._refresh_pending = True
            self.root.after_idle(self._do_scheduled_refresh)

    def _do_scheduled_refresh(self) -> None:
        self._refresh_pending = False
        events = getattr(self,'_pending_events',[])
        self._pending_events = []
        if not events: return
        kinds = {event for event,data in events}
        if kinds & {'reloaded','node_created','node_moved','node_trashed','node_restored','trash_changed'}:
            self.refresh_all()
            return
        if kinds == {'notes_changed'}:
            if any(data.get('node_id') == self.selected_id for event,data in events):
                self.inspector.refresh_current()
                if self.current_view == 'task_space': self.task_space._load_section()
            return
        if any(event == 'node_updated' and data.get('fields') != ['description'] for event,data in events):
            self.sidebar.refresh()
        title_only = bool(events) and all(event == 'node_updated' and data.get('fields') == ['title'] for event,data in events)
        if title_only and self.current_view == 'activity':
            self.activity_page.refresh_labels()
        elif not all(event == 'node_updated' and data.get('fields') == ['description'] for event,data in events):
            self._reload_center()
        if any(not data.get('node_id') or data.get('node_id') == self.selected_id for event,data in events):
            self.inspector.refresh_current()
        if self.dashboard is not None and self.dashboard.winfo_exists() and not title_only:
            self.dashboard.refresh()

    def refresh_all(self) -> None:
        self._pending_events = []
        if self.ws is None:
            return
        if self.selected_id and self.selected_id not in self.ws.nodes:
            self.selected_id = None
        if self.current_scope and self.current_scope not in self.ws.nodes:
            self.current_scope = None
            self.current_view = "today"
        self.sidebar.refresh()
        self._reload_center()
        self.inspector.refresh_current() if self.selected_id else self.inspector.load(None)
        if self.dashboard is not None:
            if self.dashboard.winfo_exists():
                self.dashboard.refresh()
            else:
                self.dashboard = None

    def open_dashboard(self) -> None:
        if self.ws is None:
            return
        if self.dashboard is not None and self.dashboard.winfo_exists():
            self.dashboard.project_id = self.activity_page._project_options.get(self.activity_page.project.get(), "*")
            self.dashboard.focus_projects = self.activity_page._focus_projects
            self.dashboard.deiconify()
            self.dashboard.lift()
            self.dashboard.refresh()
            return
        self.dashboard = DashboardWindow(self)

    def live_session(self) -> tuple[str, float] | None:
        t = self.timer
        return (t.node_id, t.seconds) if t is not None and t.active and t.node_id else None

    def _reload_center(self) -> None:
        v = self.current_view
        if v == "task_space":
            self._show_center(self.task_space)
            self.task_space.refresh()
        elif v == "today":
            self._show_center(self.today)
            self.today.refresh()
        elif v == "calendar":
            self._show_calendar()
        elif v == "activity":
            self._show_center(self.activity_page)
            self.activity_page.refresh()
        else:
            self._show_center(self.tasklist)
            self._configure_list()

    def _show_center(self, widget: tk.Misc) -> None:
        self._sync_inspector()
        self.sidebar.show_hierarchy(self.current_view.startswith(("tasks","tree:","search:")) or self.current_view == "archive")
        for w in (self.tasklist, self.today, self.calendar_page, self.activity_page, self.task_space):
            if w is not None and w is not widget:
                w.pack_forget()
        if not widget.winfo_ismapped():
            widget.pack(fill="both", expand=True)

    def _show_calendar(self) -> None:
        self._show_center(self.calendar_page)
        self.calendar_page.refresh()

    def _configure_list(self) -> None:
        q, ws = self.q, self.ws
        v = self.current_view
        if v.startswith("search:"):
            query = v[7:]
            self.tasklist.set_source(tr('ui.app.rezultate_pentru', query=query), lambda: q.search(query), tr('ui.app.cautare_globala'),
                                     show_closed=True, empty_hint=tr('ui.app.niciun_rezultat'))
        elif v.startswith("tree:"):
            nid = self.current_scope
            node = ws.get(nid) if nid else None
            if node is None:
                return
            self.tasklist.set_source(node.title, lambda: q.tasks_in(nid), ws.breadcrumb(nid),
                                     empty_hint=tr('ui.app.niciun_task_aici_scrie_un_titlu_mai_sus_si_apasa_enter'),
                                     scope_id=nid)
        else:
            loader = q.view_archive if v == 'archive' else lambda: q.tasks(open_only=not self.tasklist.closed_var.get())
            self.tasklist.set_source(VIEW_TITLES.get(v, tr('ui.app.proiecte_si_taskuri')), loader, tr('ui.app.toate_taskurile') if v != 'archive' else tr('ui.app.elemente_arhivate'),
                                     show_closed=(v == 'archive'), empty_hint=VIEW_HINTS.get(v,''))

    def _sync_inspector(self):
        visible = self.config.show_inspector and self.selected_id is not None and self.current_view != "task_space"
        attached = str(self.inspector) in self.paned.panes()
        if visible and not attached:
            self.paned.add(self.inspector,weight=0)
            self._schedule_sashes()
        elif not visible and attached:
            self.paned.forget(self.inspector)

    def quick_tasks(self, code):
        if not self.confirm_leave():
            return
        self.show_view('tasks')
        self.tasklist.reset_filters()
        from ..domain.labels import STATUS_LABELS
        if code == 'waiting': self.tasklist.status_var.set(STATUS_LABELS[Status.WAITING])
        if code == 'todo': self.tasklist.status_var.set(STATUS_LABELS[Status.TODO])
        if code == 'done':
            self.tasklist.status_var.set(STATUS_LABELS[Status.DONE])
            self.tasklist.closed_var.set(True)
        if code == 'overdue': self.tasklist.due_var.set(tr('ui.app.restante'))
        self.tasklist.refresh()

    # ================================================================
    # Navigation
    # ================================================================
    def open_meeting(self,mid):
        if self.ws is None or not self.confirm_leave():return False
        self.show_view('calendar')
        return self.calendar_page.open_meeting(mid)

    def open_task_space(self,node_id=None):
        return self.task_space.open(node_id or self.selected_id)

    def toggle_task_focus(self,event=None):
        if self.current_view == 'task_space': self.task_space.toggle_focus()
        return 'break'

    def confirm_leave(self) -> bool:
        meetings=self.calendar_page.meetings
        if not meetings.resolve():return False
        if self.followup_dialog is not None and self.followup_dialog.winfo_exists():
            self.followup_dialog.lift();return False
        details = self.inspector.tab_by_id("details")
        for editor in (details.editor, self.task_space.editor):
            guide = getattr(editor, "guide_dialog", None)
            if guide is not None and guide.winfo_exists():
                guide.lift()
                return False
        expanded = getattr(details, "expanded", None)
        if expanded is not None and expanded.winfo_exists():
            expanded.lift()
            return False
        if self.ws is None or not (self.inspector.is_dirty() or (self.current_view == "task_space" and self.task_space.is_dirty())):
            return True
        ans = ask_choice(self.root, tr('ui.tab_details.modificari_nesalvate'),
                         tr('ui.app.exista_modificari_nesalvate_in_task'),
                         [("save", tr('ui.settings_dialog.salveaza')), ("discard", tr('ui.tab_details.renunta_la_modificari')), ("cancel", tr('ui.meetings.ramai_aici'))])
        if ans == "save":
            return self.task_space.save() if self.current_view == "task_space" else self.inspector.save()
        if ans == "discard":
            if self.current_view == "task_space" and self.task_space.node_id not in self.ws.nodes:
                self.task_space.discard_missing()
            self.inspector.revert()
            return True
        return False

    def show_view(self, key: str, select_sidebar: bool = False) -> None:
        legacy = {'inbox':'todo','waiting':'waiting','overdue':'overdue','completed':'done'}
        if key in legacy:
            self.quick_tasks(legacy[key])
            return
        if self.ws is None:
            return
        if not self.confirm_leave():
            self._restore_selection_widgets()
            return
        if self.current_view == "task_space": self.task_space.leave_route()
        self.current_view = key
        self.config.last_view = key if key in ("today","tasks","calendar","activity") else "tasks"
        self.config.save()
        self.current_scope = None
        self.sidebar.select_view(key)
        self.selected_id = None
        self.inspector.load(None)
        self._reload_center()

    def show_node_scope(self, node_id: str) -> None:
        if self.ws is None or node_id not in self.ws.nodes:
            return
        if not self.confirm_leave():
            self._restore_selection_widgets()
            return
        if self.current_view == "task_space": self.task_space.leave_route()
        self.config.last_view = "tasks"
        self.current_view = f"tree:{node_id}"
        self.current_scope = node_id
        self.selected_id = node_id
        self.sidebar.select_node(node_id)
        self.inspector.load(node_id)
        self._show_center(self.tasklist)
        self._configure_list()
        self.tasklist.clear_selection()

    def select_node(self, node_id: str, source: str = "program", reveal: bool = False) -> None:
        if self.ws is None or node_id not in self.ws.nodes:
            return
        if self.current_view == 'task_space' and node_id != self.task_space.node_id:
            if self.ws.get(node_id).kind == Kind.TASK:
                self.open_task_space(node_id)
                return
            if not self.confirm_leave(): return
            self.task_space.leave_route()
            self.current_view='tasks'
        if node_id == self.selected_id and source == "list":
            return
        if not self.confirm_leave():
            self._restore_selection_widgets()
            return
        if reveal:
            self.config.last_view = "tasks"
            node = self.ws.nodes[node_id]
            scope = self._scope_for(node)
            self.current_view = f"tree:{scope}"
            self.current_scope = scope
            self.selected_id = node_id
            self.sidebar.select_node(scope)
            self._show_center(self.tasklist)
            self._configure_list()
            self.tasklist.select(node_id)
        else:
            self.selected_id = node_id
        self.inspector.load(node_id,keep_dirty=self.current_view == "task_space")
        self._sync_inspector()
        self.update_session_buttons()

    def _scope_for(self, node: Node) -> str:
        """Lista centrala ramane pe contextul curent daca nodul apartine lui; altfel pe cel mai apropiat container."""
        ws = self.ws
        cur = self.current_scope
        if cur is not None and cur in ws.nodes and (node.id == cur or cur in {a.id for a in ws.ancestors(node.id)}):
            return cur
        if node.kind != Kind.TASK:
            return node.id
        for anc in reversed(ws.ancestors(node.id)):
            if anc.kind != Kind.TASK:
                return anc.id
        return node.parent_id if node.parent_id in ws.nodes else node.id

    def _restore_selection_widgets(self) -> None:
        if self.current_scope:
            self.sidebar.select_node(self.current_scope)
        elif self.current_view in VIEW_TITLES:
            self.sidebar.select_view(self.current_view)
        if self.selected_id:
            self.tasklist.select(self.selected_id)

    def focus_inspector(self) -> None:
        self.inspector.show_tab("Detalii")
        tab = self.inspector.tab_by_id("details")
        if tab is not None and hasattr(tab, "title_entry"):
            tab.title_entry.focus_set()  # type: ignore[attr-defined]

    def after_inspector_save(self, node_id: str) -> None:
        self.inspector.refresh_current()
        self.sidebar.refresh()
        self.tasklist.refresh()
        if self.today.winfo_ismapped():
            self.today.refresh()
        if self.current_view == "task_space": self.task_space.refresh()

    # ================================================================
    # Search
    # ================================================================
    def _debounce_search(self) -> None:
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(300, self._run_search)

    def _run_search(self) -> None:
        self._search_job = None
        text = self.search_var.get().strip()
        if self.ws is None:
            return
        if not text:
            if self.current_view.startswith("search:"):
                self.show_view("tasks", select_sidebar=True)
            return
        if self.current_view != f"search:{text}":
            if not self.confirm_leave():
                return
            if self.current_view == "task_space": self.task_space.leave_route()
            self.config.last_view = "tasks"
            self.current_view = f"search:{text}"
            self.current_scope = None
            self.selected_id = None
            self.sidebar.clear_selection()
            self.inspector.load(None)
            self._show_center(self.tasklist)
            self._configure_list()

    def _clear_search(self) -> None:
        self.search_var.set("")

    # ================================================================
    # Write guard
    # ================================================================
    def run_write(self, fn: Callable[[], Any], *, success_text: str = tr('ui.tab_details.salvat'), refresh: bool = False) -> bool:
        if self.ws is None:
            return False
        try:
            fn()
        except ExternalModificationError as exc:
            self.status.set_save_error(tr('ui.app.conflict_modificat_extern'))
            self._handle_external_modification(str(exc))
            return False
        except ReadOnlyError:
            show_error(self.root, tr('ui.app.workspace_ul_este_deschis_doar_pentru_citire'))
            return False
        except FocusDeskError as exc:
            self.status.set_save_error(tr('ui.statusbar.eroare_la_salvare'))
            show_error(self.root, str(exc))
            return False
        except Exception as exc:
            log.exception("Eroare neașteptată la scriere")
            self.status.set_save_error(tr('ui.statusbar.eroare_la_salvare'))
            show_error(self.root, tr('ui.app.eroare_neasteptata', exc=exc))
            return False
        self.status.set_saved()
        if refresh:
            self.refresh_all()
        return True

    def _handle_external_modification(self, message: str) -> None:
        ans = ask_choice(self.root, tr('ui.app.fisier_modificat_extern'),
                         tr('ui.app.aplicatia_nu_suprascrie_silentios_modificarile_facute_din_afara_reinca', message=message),
                         [("reload", tr('ui.meetings.reincarca_de_pe_disc')), ("cancel", tr('ui.meetings.anuleaza'))])
        if ans == "reload" and self.ws:
            self.ws.reload()
            self.refresh_all()

    def save_current(self) -> None:
        meetings=self.calendar_page.meetings
        if self.current_view=='calendar' and meetings.mid and self.calendar_page.nb.select()==str(meetings):
            meetings.save();return
        if self.current_view == "task_space":
            self.task_space.save()
            return
        if self.ws is None:
            return
        if self.inspector.is_dirty():
            self.inspector.save()
        else:
            self.status.set_message(tr('ui.app.nimic_de_salvat_modificarile_se_scriu_imediat_pe_disc'))

    # ================================================================
    # Node actions
    # ================================================================
    def _default_parent_for_new(self, kind: Kind) -> str | None:
        """Locatia implicita: contextul curent (folder/proiect), sau parintele task-ului selectat."""
        ws = self.ws
        nid = self.current_scope or self.selected_id
        if nid is None or nid not in ws.nodes:
            return None
        node = ws.nodes[nid]
        candidates = [node.id] + [a.id for a in reversed(ws.ancestors(node.id))]
        for cid in candidates:
            try:
                ws.check_parent(kind, cid)
                return cid
            except FocusDeskError:
                continue
        return None

    def new_node(self, kind: Kind, parent_id: str | None = ..., title: str = "") -> Node | None:  # type: ignore[assignment]
        if self.ws is None:
            return None
        if self.ws.read_only:
            show_error(self.root, tr('ui.app.workspace_ul_este_deschis_doar_pentru_citire'))
            return None
        if not self.confirm_leave():
            return None
        if parent_id is ...:
            parent_id = self._default_parent_for_new(kind)
        res = NewNodeDialog(self.root, self.ws, kind=kind, parent_id=parent_id, title=title).run()
        if not res:
            return None
        created: list[Node] = []
        ok = self.run_write(lambda: created.append(self.ws.create_node(
            res["kind"], res["title"], res["parent_id"], res["description"], **res["fields"])))
        if not ok:
            return None
        node = created[0]
        self.refresh_all()
        self.select_node(node.id, reveal=True)
        return node

    def new_from_template(self):
        if self.ws is None:return
        if self.ws.read_only:
            show_error(self.root,tr('ui.app.workspace_ul_este_deschis_doar_pentru_citire'))
            return
        if not self.confirm_leave():return
        from .templates_ui import CreateTemplateDialog
        CreateTemplateDialog(self)

    def manage_templates(self):
        if self.ws is None:return
        from .templates_ui import TemplateManager
        TemplateManager(self)

    def save_as_template(self,node_id):
        if self.ws is None or self.ws.read_only or not self.confirm_leave():return
        from .templates_ui import TemplateEditor
        name=ask_string(self.root,tr('ui.app.salveaza_ca_sablon'),tr('ui.app.nume_sablon'),initial=self.ws.get(node_id).title[:200])
        if not name:return
        try:
            template=self.ws.templates.capture(node_id,name)
            TemplateEditor(self,template)
        except Exception as exc:show_error(self.root,str(exc))

    def new_subtask(self) -> None:
        nid = self.selected_id
        if not nid or self.ws is None or self.ws.nodes[nid].kind != Kind.TASK:
            show_info(self.root, tr('ui.app.selecteaza_intai_un_task_pentru_a_i_adauga_un_subtask'))
            return
        self.new_node(Kind.TASK, parent_id=nid)

    def quick_add_task(self, parent_id: str | None, title: str) -> bool:
        """Task rapid (doar titlu) sub un container sau un alt task; la orice adancime."""
        if self.ws is None or (parent_id is not None and parent_id not in self.ws.nodes):
            return False
        return self.run_write(lambda: self.ws.create_node(Kind.TASK, title, parent_id), refresh=True)

    def reorder_selected(self, direction: int) -> None:
        node = self._selected_node()
        if node is not None and self.run_write(lambda: self.ws.reorder(node.id, direction), refresh=True):
            self.tasklist.select(node.id)

    def indent_selected(self) -> None:
        """Face din task-ul selectat un subtask al fratelui de deasupra lui."""
        node = self._selected_node()
        if node is None or node.kind != Kind.TASK:
            return
        siblings = self.ws.children(node.parent_id if node.parent_id in self.ws.nodes else None)
        idx = next((i for i, n in enumerate(siblings) if n.id == node.id), 0)
        prev = siblings[idx - 1] if idx > 0 else None
        if prev is None or prev.kind != Kind.TASK:
            show_info(self.root, tr('ui.app.task_ul_trebuie_sa_aiba_deasupra_lui_pe_acelasi_nivel_un_alt_task_caru'))
            return
        if self.run_write(lambda: self.ws.move(node.id, prev.id), refresh=True):
            self.tasklist.select(node.id)

    def outdent_selected(self) -> None:
        """Scoate task-ul selectat cu un nivel, imediat după părintele lui."""
        node = self._selected_node()
        if node is None or node.kind != Kind.TASK:
            return
        parent = self.ws.nodes.get(node.parent_id) if node.parent_id else None
        if parent is None or parent.kind != Kind.TASK:
            show_info(self.root, tr('ui.app.task_ul_este_deja_la_primul_nivel_al_containerului_sau'))
            return
        if self.run_write(lambda: self.ws.move(node.id, parent.parent_id, parent.sort_order + 5), refresh=True):
            self.tasklist.select(node.id)

    def compose_mail(self, node_id: str | None = None, *, attachments=()) -> None:
        """E-mail din task prin Outlook Classic; trimiterea porneste doar din dialog, dupa confirmare."""
        if self.ws is None:
            return
        nid = node_id or self.selected_id
        node = self.ws.nodes.get(nid) if nid else None
        if node is None:
            show_info(self.root, tr('ui.app.selecteaza_un_task_din_care_sa_trimiti_e_mailul'))
            return
        if self._mail_composing:
            if self.mail_dialog is not None and self.mail_dialog.winfo_exists():
                if self.mail_dialog.ws is self.ws and self.mail_dialog.node_id == node.id and attachments:
                    self.mail_dialog._select_attachments(attachments)
                self.mail_dialog.lift()
            return
        ws = self.ws
        self._mail_composing = True
        try:
            description = None
            details = self.inspector.tab_by_id("details")
            if details.node_id == node.id:
                current = details.desc.get("1.0", "end-1c")
                if current != details._orig_desc:
                    choice = DescriptionSourceDialog(self.root).run()
                    if choice not in ("current", "saved"):
                        return
                    if choice == "current":
                        description = current
            if self.ws is not ws or node.id not in ws.nodes:
                return
            self.mail_dialog = MailDialog(self.root, self, node, description=description)
            if attachments:
                self.mail_dialog._select_attachments(attachments)
            self.mail_dialog.run()
        except FocusDeskError as exc:
            show_error(self.root, str(exc), "E-mail")
        finally:
            self.mail_dialog = None
            self._mail_composing = False

    def record_mail_result(self, ws, node_id, draft, result) -> str:
        """Record only the actual outcome in the captured workspace; never retry transport."""
        text = {"displayed": tr('ui.app.ciorna_este_deschisa_in_outlook_fara_trimitere'),
                "submitted": tr('ui.app.mesaj_predat_outlook_pentru_trimitere_livrarea_efectiva_nu_este_confir'),
                "uncertain": tr('ui.app.rezultat_e_mail_incert_verifica_in_outlook_inaintea_unei_noi_incercari')}.get(result) if isinstance(result,str) else None
        if text is None:
            from ..services.gmail import result_notice
            text=result_notice(result)
        if self.ws is not ws or ws.read_only or node_id not in ws.nodes:
            return text + tr('ui.app.jurnalul_nu_a_fost_scris_workspace_schimbat_read_only_sau_task_indispo')
        try:
            ws.add_note(node_id, journal_text(draft, result), kind="action")
        except Exception as exc:
            log.exception("Rezultat e-mail confirmat, jurnal local nescris")
            return text + tr('ui.app.jurnalul_local_nu_a_putut_fi_scris_nu_retrimite_pentru_a_repara_jurnal', exc=exc)
        # Do not reload Details or discard unrelated unsaved task fields.
        try:
            journal = self.inspector.tab_by_id('journal')
            if self.inspector.node_id == node_id and self.inspector.nb.select() == str(journal):
                journal.load(ws.get(node_id))
        except Exception:
            log.exception("Jurnalul e-mail a fost scris, dar afișarea lui nu s-a actualizat")
        return text + tr('ui.app.rezultatul_este_notat_in_activitatea_taskului')

    def _selected_node(self) -> Node | None:
        if self.ws is None or not self.selected_id:
            return None
        return self.ws.nodes.get(self.selected_id)

    def rename_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        title = ask_string(self.root, tr('ui.app.redenumeste'), tr('ui.app.titlu_nou_directorul_fizic_si_uuid_ul_raman_neschimbate'),
                           node.title, tr('ui.app.redenumeste'))
        if title and title != node.title:
            if self.run_write(lambda: self.ws.rename(node.id, title), refresh=True):
                self.inspector.load(node.id)

    def move_selected(self) -> None:
        if not self.confirm_leave():
            return
        node = self._selected_node()
        if node is None:
            return
        res = MoveDialog(self.root, self.ws, node).run()
        if res is None:
            return
        (new_parent,) = res
        if new_parent == node.parent_id:
            return
        if self.run_write(lambda: self.ws.move(node.id, new_parent), refresh=True):
            self.select_node(node.id, reveal=True)

    def link_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        picked = NodePickerDialog(self.root, self.ws, tr('ui.tab_details.legatura_catre'), exclude={node.id, *node.related_node_ids}).run()
        if picked:
            self.run_write(lambda: self.ws.add_related(node.id, picked), refresh=True)

    def toggle_pin_selected(self) -> None:
        node = self._selected_node()
        if node is not None and node.kind == Kind.TASK:
            self.set_pinned(node.id, node.pinned_today != self.q.today())

    def set_pinned(self, node_id: str, pinned: bool) -> None:
        day = self.q.today() if pinned else None
        self.run_write(lambda: self.ws.update_node(node_id, pinned_today=day), refresh=True)

    def toggle_done_selected(self) -> None:
        if not self.confirm_leave():
            return
        node = self._selected_node()
        if node is None or node.kind == Kind.FOLDER:
            return
        new = Status.TODO if node.status in CLOSED_STATUSES else Status.DONE
        if new == Status.DONE and self.ws.future_sessions(node.id):
            ans = ask_choice(self.root, tr('ui.app.sesiuni_viitoare'),
                             tr('ui.app.task_ul_are_sesiuni_planificate_in_viitor_le_anulez'),
                             [("cancel", tr('ui.app.anuleaza_sesiunile')), ("keep", tr('ui.app.pastreaza_le')), ("abort", tr('ui.app.nu_finaliza'))])
            if ans in (None, "abort"):
                return
            if ans == "cancel":
                self.run_write(lambda: self.ws.cancel_sessions(self.ws.future_sessions(node.id)))
        self.run_write(lambda: self.ws.reopen_task(node.id) if new==Status.TODO and node.kind==Kind.TASK else self.ws.update_node(node.id,status=new), refresh=True)

    def add_followup(self,node_id=None):
        node_id=node_id or self.selected_id
        if not self.ws or self.ws.read_only or node_id not in self.ws.nodes or self.ws.get(node_id).kind!=Kind.TASK:return None
        if self.followup_dialog is not None and self.followup_dialog.winfo_exists():
            self.followup_dialog.lift();return self.followup_dialog
        modal=self.root.grab_current()
        if isinstance(modal,tk.Toplevel):modal.lift();return None
        from .followups import FollowupDialog
        self.followup_dialog=FollowupDialog(self,node_id)
        return self.followup_dialog

    def reopen_with_reason(self,node_id=None):
        node_id=node_id or self.selected_id
        if not self.ws or self.ws.read_only or node_id not in self.ws.nodes or self.ws.get(node_id).status not in CLOSED_STATUSES:return
        if not self.confirm_leave():return
        from .followups import ReopenReasonDialog
        return ReopenReasonDialog(self,node_id)

    def toggle_archive_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        if node.archived_at is not None:
            self.run_write(lambda: self.ws.unarchive(node.id), refresh=True)
            return
        policy = "keep"
        if self.ws.future_sessions(node.id):
            ans = ask_choice(self.root, tr('ui.app.sesiuni_viitoare'),
                             tr('ui.app.nodul_are_sesiuni_planificate_in_viitor_ce_faci_cu_ele'),
                             [("keep", tr('ui.app.pastreaza_le')), ("cancel", tr('ui.app.anuleaza_le')), ("abort", tr('ui.app.nu_arhiva'))])
            if ans in (None, "abort"):
                return
            policy = ans
        self.run_write(lambda: self.ws.archive(node.id, future_sessions=policy), refresh=True)

    def trash_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        n = len(self.ws.subtree_ids(node.id))
        extra = tr('ui.app.si_descendenti', n_1=n - 1) if n > 1 else ""
        if confirm(self.root, tr('ui.app.muti_in_cos_poti_restaura_din_fisier_cos', node_title=node.title, extra=extra)):
            if self.run_write(lambda: self.ws.trash(node.id), refresh=True):
                self.selected_id = None
                self.inspector.load(None)

    # ---- context menu -----------------------------------------------
    def popup_context_menu(self, x: int, y: int, node_id: str | None) -> None:
        if self.ws is None:
            return
        node = self.ws.nodes.get(node_id) if node_id else None
        if node is not None:
            if node.id != self.selected_id and not self.confirm_leave():
                return
            self.selected_id = node.id
            self.inspector.load(node.id, keep_dirty=True)
        menu = tk.Menu(self.root, tearoff=False)
        ro = self.ws.read_only
        state = "disabled" if ro else "normal"
        if node is None:
            menu.add_command(label=tr('ui.app.task_nou'), command=lambda: self.new_node(Kind.TASK, parent_id=None), state=state)
            menu.add_command(label=tr('ui.app.folder_nou'), command=lambda: self.new_node(Kind.FOLDER, parent_id=None), state=state)
            menu.add_command(label=tr('ui.app.proiect_nou'), command=lambda: self.new_node(Kind.PROJECT, parent_id=None), state=state)
        else:
            if node.kind == Kind.TASK:
                menu.add_command(label=tr('ui.app.deschide_spatiul_de_lucru'),command=lambda:self.open_task_space(node.id))
                menu.add_command(label=tr('ui.app.subtask_nou'), command=lambda: self.new_node(Kind.TASK, parent_id=node.id),
                                 state=state)
                if self.timer_active() and self.timer.node_id==node.id:
                    menu.add_command(label=tr('ui.app.incheie_sesiunea'), command=self.stop_session)
                else:
                    menu.add_command(label=tr('ui.app.incepe_sesiune_2'), command=lambda: self.start_session(node.id),
                                     state=state)
                menu.add_command(label=tr('ui.app.redeschide_taskul') if node.status in CLOSED_STATUSES else tr('ui.app.finalizeaza_taskul'), command=self.toggle_done_selected, state=state)
                menu.add_command(label=tr('ui.app.adauga_cerinta_noua'),command=lambda:self.add_followup(node.id),state=state)
                if node.status in CLOSED_STATUSES:
                    menu.add_command(label=tr('ui.app.redeschide_cu_motiv'),command=lambda:self.reopen_with_reason(node.id),state=state)
                menu.add_command(label=tr('ui.app.prioritate_pentru_azi_comuta'), command=self.toggle_pin_selected, state=state)
            else:
                menu.add_command(label=tr('ui.app.task_nou_aici'), command=lambda: self.new_node(Kind.TASK, parent_id=node.id),
                                 state=state)
                menu.add_command(label=tr('ui.app.folder_nou_aici'), command=lambda: self.new_node(Kind.FOLDER, parent_id=node.id),
                                 state=state)
                if node.kind == Kind.FOLDER:
                    menu.add_command(label=tr('ui.app.proiect_nou_aici'),
                                     command=lambda: self.new_node(Kind.PROJECT, parent_id=node.id), state=state)
            if node.kind in (Kind.PROJECT,Kind.TASK):
                menu.add_command(label=tr('ui.app.salveaza_ca_sablon_2'),command=lambda:self.save_as_template(node.id),state=state)
            menu.add_separator()
            menu.add_command(label=tr('ui.app.redenumeste_f2'), command=self.rename_selected, state=state)
            menu.add_command(label=tr('ui.app.muta'), command=self.move_selected, state=state)
            if node.kind == Kind.TASK:
                menu.add_command(label=tr('ui.app.face_subtask_al_celui_de_deasupra_alt'), command=self.indent_selected,
                                 state=state)
                menu.add_command(label=tr('ui.app.scoate_un_nivel_alt'), command=self.outdent_selected, state=state)
            menu.add_command(label=tr('ui.app.adauga_legatura'), command=self.link_selected, state=state)
            menu.add_command(label=tr('ui.app.trimite_e_mail_ctrl_m'), command=lambda: self.compose_mail(node.id))
            self._extend_context_menu(menu, node)
            menu.add_separator()
            menu.add_command(label=tr('ui.app.dezarhiveaza') if node.archived_at else tr('ui.app.arhiveaza'),
                             command=self.toggle_archive_selected, state=state)
            menu.add_command(label=tr('ui.app.trimite_in_cos'), command=self.trash_selected, state=state)
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _extend_context_menu(self, menu: tk.Menu, node: Node) -> None:
        menu.add_separator()
        menu.add_command(label=tr('ui.app.deschide_folderul_nodului'), command=lambda: self.open_node_folder(node.id))
        if node.kind != Kind.FOLDER and self.files.usable_source_dir(node.id) is not None:
            menu.add_command(label=tr('ui.app.deschide_codul_in_vs_code'), command=lambda: self.open_code_in_vscode(node.id))

    # ================================================================
    # Workspace / file menu
    # ================================================================
    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.delete(0, "end")
        for p in self.config.recent_workspaces:
            self.recent_menu.add_command(label=p, command=lambda p=p: self.open_workspace(Path(p)))
        if not self.config.recent_workspaces:
            self.recent_menu.add_command(label=tr('common.none'), state="disabled")

    def menu_open_workspace(self) -> bool:
        d = filedialog.askdirectory(parent=self.root, title=tr('ui.app.alege_folderul_workspace_ului'),
                                    initialdir=self.config.last_workspace or str(Path.home()))
        if not d:
            return False
        p = Path(d)
        if not (p / "workspace.json").is_file():
            show_error(self.root, tr('ui.app.folderul_ales_nu_contine_un_workspace_focusdesk_lipseste_workspace_jso'))
            return False
        return self.open_workspace(p)

    def menu_new_workspace(self) -> bool:
        d = filedialog.askdirectory(parent=self.root, title=tr('ui.app.alege_folderul_in_care_se_creeaza_workspace_ul'),
                                    initialdir=str(Path.home() / "Documents"))
        if not d:
            return False
        p = Path(d)
        if (p / "workspace.json").is_file():
            return self.open_workspace(p)
        if p.exists() and any(p.iterdir()):
            p = p / "FocusDeskData"
            if p.exists() and any(p.iterdir()):
                show_error(self.root, tr('ui.app.exista_deja_si_nu_este_gol', p=p))
                return False
            if not confirm(self.root, tr('ui.app.folderul_ales_nu_este_gol_creez_workspace_ul_in', p=p)):
                return False
        name = ask_string(self.root, tr('ui.app.workspace_nou_2'), tr('ui.app.nume_afisat'), "FocusDesk", tr('ui.planning.creeaza')) or "FocusDesk"
        return self.open_workspace(p, create=True, name=name)

    def menu_demo_workspace(self) -> bool:
        from ..services.demo import create_demo_workspace

        d = filedialog.askdirectory(parent=self.root, title=tr('ui.app.alege_un_folder_gol_pentru_workspace_ul_demonstrativ'),
                                    initialdir=str(Path.home() / "Documents"))
        if not d:
            return False
        p = Path(d)
        if p.exists() and any(p.iterdir()):
            p = p / "FocusDeskDemo"
            if p.exists() and any(p.iterdir()):
                show_error(self.root, tr('ui.app.exista_deja_si_nu_este_gol', p=p))
                return False
        if not self._release_current():
            return False
        try:
            create_demo_workspace(p)
        except FocusDeskError as exc:
            show_error(self.root, str(exc))
            return False
        return self.open_workspace(p)

    def reload_preserving_context(self):
        if self.ws is None: return
        dirty = {tab.node_id for tab in self.inspector.tabs if tab.node_id and
                 (tab.is_dirty() or getattr(tab,'expanded',None) is not None)}
        self.ws.reload(protect_node_ids=dirty)
        self.refresh_all()

    def rescan(self) -> None:
        if self.ws is None or not self.confirm_leave():
            return
        self.ws.reload()
        self.refresh_all()
        errors = sum(1 for i in self.ws.issues if i.severity == "error")
        warns = len(self.ws.issues) - errors
        self.status.set_message(tr('ui.app.rescanat_noduri_erori_avertismente', len_self_ws_nodes=len(self.ws.nodes), errors=errors, warns=warns))
        if self.ws.issues:
            IssuesDialog(self.root, self.ws).run()

    def show_issues(self) -> None:
        if self.ws:
            IssuesDialog(self.root, self.ws).run()

    def open_trash(self) -> None:
        if self.ws:
            TrashDialog(self.root, self.ws, self.refresh_all).run()

    def backup_now(self, full: bool) -> None:
        ws = self.ws
        if ws is None or ws.read_only:
            show_error(self.root, tr('ui.app.backup_ul_necesita_un_workspace_editabil'))
            return
        if not self.calendar_page.meetings.resolve():return
        self.status.set_message(tr('ui.app.se_creeaza_backup_ul'))

        def done(res) -> None:
            msg = tr('backup.full_created' if full else 'backup.meta_created',path=res.path,files=res.file_count)
            msg += tr('ui.app.atentie_un_backup_pe_acelasi_disc_nu_protejeaza_de_defectarea_discului')
            if res.external_copy:
                msg += tr('ui.app.copie_externa', res_external_copy=res.external_copy)
            if res.external_error:
                msg += tr('ui.app.copia_externa_a_esuat', res_external_error=res.external_error)
            self.status.set_message(tr('ui.app.backup_creat'))
            show_info(self.root, msg, tr('ui.settings_dialog.backup'))

        self._track_workspace_job(self.bridge.submit(lambda tok: backup_service.create_backup(ws, full=full), on_done=done,
                           on_error=lambda e: (self.status.set_message(""), show_error(self.root, str(e))),
                           name="backup"))

    def restore_backup(self) -> None:
        zp = filedialog.askopenfilename(parent=self.root, title=tr('ui.app.alege_arhiva_de_backup'),
                                        filetypes=[(tr('ui.app.backup_focusdesk'), "*.zip")])
        if not zp:
            return
        d = filedialog.askdirectory(parent=self.root, title=tr('ui.tab_versions.alege_un_folder_gol_pentru_restaurare'))
        if not d:
            return
        try:
            out = backup_service.restore_backup_to_folder(Path(zp), Path(d))
        except FocusDeskError as exc:
            show_error(self.root, str(exc))
            return
        if confirm(self.root, tr('ui.app.backup_restaurat_in_il_deschid_acum_ca_workspace', out=out)):
            self.open_workspace(out)

    # ================================================================
    # View toggles / theme
    # ================================================================
    def toggle_theme(self) -> None:
        mode = "light"
        self.dark_var.set(False)
        self.config.theme = mode
        self.config.save()
        apply_theme(self.root, mode)
        if self.ws is not None:
            from .common import muted_color

            self.tasklist.configure_tags()
            self.sidebar.tree.tag_configure("closed", foreground=muted_color(self.root))
            self.sidebar.tree.tag_configure("archived", foreground=muted_color(self.root))
            self.refresh_all()
            self.inspector.tab_by_id("details").sf.sync_background()  # type: ignore[union-attr]

    def toggle_inspector(self) -> None:
        self.config.show_inspector = self.inspector_var.get()
        if self.config.show_inspector:
            if str(self.inspector) not in self.paned.panes():
                self.paned.add(self.inspector, weight=0)
                self._schedule_sashes(50)
        else:
            if str(self.inspector) in self.paned.panes():
                self.paned.forget(self.inspector)
        self._sync_inspector()
        self.config.save()

    def toggle_completed(self) -> None:
        if not self.confirm_leave():
            self.completed_var.set(self.config.show_completed)
            return
        self.config.show_completed = self.completed_var.get()
        self.config.save()
        self.sidebar.refresh()

    def toggle_archived(self) -> None:
        self.config.show_archived = self.archived_var.get()
        self.config.save()
        self.sidebar.refresh()

    def open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        if SettingsDialog(self.root, self).run() and self.ws is not None:
            self.refresh_all()

    def show_guide(self, chapter=None, *, contextual=False):
        return self.user_guide.open(chapter, contextual=contextual)

    def show_shortcuts(self) -> None:
        self.show_guide('scurtaturi')

    def show_about(self) -> None:
        show_info(self.root, tr('ui.app.focusdesk_organizator_personal_local_fisiere_json_markdown_fara_baze_d', version=__version__), tr('ui.app.despre'))

    # ================================================================
    # Sessions / timer
    # ================================================================
    def timer_active(self) -> bool:
        return bool(self.timer and self.timer.active)

    def last_worked_node(self) -> Node | None:
        if self.ws is None:
            return None
        sessions = [s for s in self.ws.repo.sessions.list_all() if s.status == "done" and s.stopped_actual_at]
        sessions.sort(key=lambda s: s.stopped_actual_at, reverse=True)  # type: ignore[arg-type, return-value]
        for s in sessions:
            n = self.ws.nodes.get(s.node_id)
            if n is not None and n.status not in CLOSED_STATUSES and n.archived_at is None:
                return n
        return None

    def resume_work(self) -> None:
        if self.timer_active():
            self.select_node(self.timer.node_id, reveal=True)  # type: ignore[union-attr, arg-type]
            return
        node = self.last_worked_node()
        if node is None:
            show_info(self.root, tr('ui.app.nu_exista_inca_o_sesiune_anterioara_de_reluat'))
            return
        self.select_node(node.id, reveal=True)
        self.start_session(node.id)

    def start_selected_session(self) -> None:
        node = self._selected_node()
        if node is None or node.kind != Kind.TASK:
            show_info(self.root, tr('ui.app.selecteaza_un_task_pentru_a_incepe_o_sesiune'))
            return
        self.start_session(node.id)

    def start_session(self, node_id: str, planned_session_id: str | None = None) -> None:
        if getattr(self,'_starting_session',False) or getattr(self,'_stopping_session',False):return
        self._starting_session=True
        try:return self._start_session(node_id,planned_session_id)
        finally:self._starting_session=False

    def _start_session(self, node_id, planned_session_id=None):
        if not self.confirm_leave():
            return
        if self.ws is None or self.timer is None:
            return
        if self.ws.read_only:return
        if self.timer.recovered:
            self._handle_recovered_timer()
            if self.timer.recovered:return
        if self.timer.state:
            if self.timer.node_id == node_id:
                self.select_node(node_id,reveal=True)
                return
            choice=ask_choice(self.root,tr('ui.app.sesiune_curenta'),
                tr('ui.app.exista_deja_o_sesiune_de_lucru_inclusiv_in_pauza_ce_doresti_sa_faci'),
                [('continue',tr('ui.app.continua_sesiunea_existenta')),('finish',tr('ui.app.incheie_sesiunea_si_incepe_taskul_ales')),('cancel',tr('ui.meetings.anuleaza'))])
            if choice=='continue':
                if not self.timer.running:self.run_write(self.timer.resume)
                self.select_node(self.timer.node_id,reveal=True)
                return
            if choice!='finish' or not self.stop_session():return
        node = self.ws.nodes.get(node_id)
        if node is None:
            return
        blockers = self.ws.unfinished_dependencies(node_id)
        if blockers and not confirm(self.root, tr('ui.app.task_ul_depinde_de_task_uri_nefinalizate') +
                                    "\n• ".join(b.title for b in blockers) + "\n\nContinui oricum?"):
            return
        open_opts = self._ask_session_open_options(node)
        if open_opts is False:
            return
        ok = self.run_write(lambda: self.timer.start(node_id, planned_session_id), success_text=tr('ui.app.in_lucru_inceput', node_title=node.title, utcnow_astimezone_self_q_tz=utcnow().astimezone(self.q.tz())))
        if not ok:
            return
        self._tick()
        self._perform_open_options(node, open_opts)
        self.refresh_all()

    def _ask_session_open_options(self, node: Node):
        """Ce se deschide la inceputul sesiunii (doar la cerere). `False` = utilizatorul a renuntat."""
        src_dir = self.files.usable_source_dir(node.id)
        openable = [a for a in node.attachments if self.files.status(node.id, a) == "ok"]
        node_folder = self.ws.node_dir(node.id)
        if src_dir is None and not openable and not node_folder.exists():
            return None
        dlg = StartSessionDialog(self.root, self, node, src_dir, len(openable))
        res = dlg.run()
        return False if res is None else res

    def _perform_open_options(self, node: Node, opts) -> None:
        if not opts:
            return
        errors: list[str] = []
        src_dir = self.files.usable_source_dir(node.id)
        try:
            if opts.get("vscode") and src_dir is not None:
                system_open.open_in_vscode(src_dir, self.ws.settings.vscode_path)
            if opts.get("explorer"):
                system_open.reveal_in_explorer(src_dir or self.ws.node_dir(node.id))
        except FocusDeskError as exc:
            errors.append(str(exc))
        if opts.get("files"):
            for att in node.attachments:
                try:
                    system_open.open_with_default_app(self.files.resolve(node.id, att))
                except FocusDeskError as exc:
                    errors.append(str(exc))
        if errors:
            show_error(self.root, "\n".join(errors), tr('ui.app.deschidere_partiala'))
        self.config.session_open = {k: bool(v) for k, v in opts.items()}
        self.config.save()

    def toggle_pause(self) -> None:
        now=time.monotonic()
        if now-getattr(self,'_last_pause_action',-1)<0.35:return
        self._last_pause_action=now
        t = self.timer
        if t is None or not t.active:
            show_info(self.root, tr('ui.app.nu_exista_o_sesiune_activa'))
            return
        if t.running:
            self.run_write(t.pause)
        else:
            gap = t.pending_gap
            if gap > 0:
                self._ask_gap(gap)
            else:
                self.run_write(t.resume)
        self._tick()

    def stop_session(self) -> bool:
        if getattr(self,'_stopping_session',False):return False
        self._stopping_session=True
        try:return self._stop_session()
        finally:self._stopping_session=False

    def _stop_session(self):
        t = self.timer
        if t is None or not t.active:
            return True
        if t.state.finalization:
            return self.run_write(t.stop,success_text=tr('ui.app.sesiune_incheiata'))
        was_running=t.running
        if not self.run_write(t.pause):return False
        node = self.ws.nodes.get(t.node_id) if t.node_id else None
        res = StopSessionDialog(self.root, self, node, t.seconds).run()
        if res is None:
            if was_running and t.state and t.state.state == "paused":
                self.run_write(t.resume)
            return False
        ok = self.run_write(lambda: t.stop(**res), success_text=tr('ui.app.sesiune_incheiata'))
        if ok:
            self._on_session_stopped(node)
            self._tick()
            self.refresh_all()
        return ok

    def _on_session_stopped(self, node: Node | None) -> None:
        """Checkpoint automat la finalul sesiunii, daca exista folder de cod si optiunea este activa."""
        if node is None or self.ws.read_only or not self.ws.settings.checkpoints.on_session_end:
            return
        if self.files.usable_source_dir(node.id) is None:
            return
        self.create_checkpoint(node.id, tr('ui.app.la_finalul_sesiunii'), trigger="session_end", quiet_if_unchanged=True)

    # ---- jobs / checkpoints / openers ---------------------------------
    def _track_workspace_job(self,job):
        self._workspace_jobs=[(ws,j) for ws,j in self._workspace_jobs if not j.done]
        self._workspace_jobs.append((self.ws,job))
        return job

    def _pending_workspace_jobs(self):
        self._workspace_jobs=[(ws,j) for ws,j in self._workspace_jobs if not j.done]
        pending=[j for ws,j in self._workspace_jobs if ws is self.ws]
        if pending:
            self.status.set_message(tr('ui.app.workspace_pastrat_deschis_asteapta_finalizarea_operatiei_locale')+pending[0].name+').')
        return bool(pending)

    def run_job(self, work: Callable[..., Any], on_done: Callable[[Any], None] | None = None, *, name: str = "job",
                busy_text: str = tr('ui.app.se_lucreaza'), on_error: Callable[[BaseException], None] | None = None) -> Job:
        """Ruleaza `work(token)` intr-un thread; callback-urile se executa pe thread-ul UI."""
        workspace=self.ws
        self._busy += 1
        self.status.set_busy(busy_text)

        def finish() -> None:
            self._busy = max(0, self._busy - 1)
            if self._busy == 0:
                self.status.clear_busy()

        def ok(res: Any) -> None:
            finish()
            if self.ws is not workspace:return
            if on_done:
                try:
                    on_done(res)
                except Exception as exc:
                    log.exception("Callback job %s a eșuat", name)
                    show_error(self.root, tr('ui.app.eroare', exc=exc))

        def err(exc: BaseException) -> None:
            finish()
            if self.ws is not workspace:return
            if on_error:
                on_error(exc)
            elif isinstance(exc, FocusDeskError):
                show_error(self.root, str(exc))
            else:
                show_error(self.root, tr('ui.app.eroare_neasteptata', exc=exc))

        return self._track_workspace_job(self.bridge.submit(work, ok, err, name=name))

    def create_checkpoint(self, node_id: str, description: str = "", *, trigger: str = "manual",
                          session_id: str | None = None, on_finished: Callable[[], None] | None = None,
                          quiet_if_unchanged: bool = False, force: bool = False) -> None:
        cs = self.checkpoints

        def done(m) -> None:
            if m is None:
                if not quiet_if_unchanged:
                    show_info(self.root, tr('ui.app.nicio_modificare_fata_de_ultimul_checkpoint_nu_s_a_creat_unul_nou'))
                self.status.set_message(tr('ui.app.checkpoint_fara_modificari'))
            else:
                self.status.set_message(tr('ui.app.checkpoint_salvat_fisiere', len_m_files=len(m.files)))
            if on_finished:
                on_finished()

        def error(exc: BaseException) -> None:
            self.status.set_message(tr('ui.app.checkpoint_esuat'))
            show_error(self.root, tr('ui.app.checkpoint_ul_nu_a_fost_salvat', exc=exc), tr('ui.app.checkpoint'))

        self.run_job(lambda tok: cs.create(node_id, description, trigger=trigger, session_id=session_id,
                                           force=force, cancel=tok),
                     done, on_error=error, name="checkpoint", busy_text=tr('ui.app.se_salveaza_checkpoint_ul'))

    # ---- calendar / planning -------------------------------------------
    def get_availability(self, start_day, end_day, on_done: Callable[[AvailabilityResult], None],
                         on_error: Callable[[BaseException], None] | None = None) -> None:
        """Disponibilitate din Outlook (daca e configurat) sau locala, cu mentiunea corecta a sursei."""
        self.outlook.get_availability(start_day, end_day, on_done, on_error)

    def availability_hint(self) -> str:
        o = self.outlook
        if o.enabled() and o.verified:
            return tr('ui.app.disponibilitate_citita_din_outlook_calendarul_ales')
        if o.enabled():
            return (tr('ui.app.outlook_este_configurat_dar_neverificat_in_aceasta_sesiune_planificare'))
        return tr('ui.app.disponibilitate_verificata_doar_local_calendarul_extern_nu_este_citit')

    def on_sessions_changed(self) -> None:
        self.sidebar.refresh()
        if self.today.winfo_ismapped():
            self.today.refresh()
        if self.current_view == "task_space": self.task_space.refresh()

    def schedule_session(self, node_id: str | None = None) -> None:
        if self.ws is None or self.ws.read_only:
            return
        if ManualSessionDialog(self.root, self, node_id or self.selected_id).run():
            self.refresh_all()

    def open_planner(self) -> None:
        if self.ws is None or self.ws.read_only:
            return
        sel = [self.selected_id] if self.selected_id and self.ws.nodes[self.selected_id].kind == Kind.TASK else None
        if PlannerDialog(self.root, self, sel).run():
            self.refresh_all()

    def open_recurrences(self) -> None:
        if self.ws is None:
            return
        RecurrenceDialog(self.root, self).run()
        self.refresh_all()

    def export_ics(self, sessions: list) -> None:
        """Export .ics: nu este sincronizare; starea ramane „Exportat — necesită import”."""
        from tkinter import filedialog

        ws = self.ws
        if not sessions:
            show_info(self.root, tr('ui.app.nu_exista_sesiuni_viitoare_de_exportat'))
            return
        path = filedialog.asksaveasfilename(parent=self.root, title=tr('ui.app.salveaza_fisierul_ics'),
                                            defaultextension=".ics", initialfile="focusdesk-sesiuni.ics",
                                            filetypes=[("iCalendar", "*.ics")])
        if not path:
            return
        include = ws.settings.outlook.include_details
        items: list[IcsItem] = []
        for s in sessions:
            n = ws.nodes.get(s.node_id)
            if n is None:
                continue
            seq = s.sync.sequence + 1
            items.append(IcsItem(s, self.sessions.title_for(n), self.sessions.description_for(n, s, include_details=include),
                                 sequence=seq, cancelled=s.status == "cancelled"))
        try:
            IcsExportProvider.export_to_file(items, ws.id, Path(path))
        except FocusDeskError as exc:
            show_error(self.root, str(exc))
            return
        stamp = datetime.now().astimezone()

        def mark() -> None:
            for it in items:
                s = it.session
                s.sync.provider = "ics"
                s.sync.state = "exported"
                s.sync.sequence = it.sequence
                s.sync.ics_uid = stable_uid(ws.id, s.id)
                s.sync.exported_at = stamp
                s.sync.signature = session_signature(s)
                ws.repo.sessions.save(s)

        self.run_write(mark, success_text=tr('extra.ui.app.ics_exportat'))
        show_info(self.root, tr('ui.app.exportat_necesita_import_in_calendar_sesiuni_scrise_in_fisierul_nu_sin', len_items=len(items), path=path),
                  tr('integrations.ics.export_ics'))

    def check_scheduled_checkpoints(self, startup: bool = False) -> None:
        """Checkpoint zilnic programat (doar cat ruleaza aplicatia); ora ratata se raporteaza explicit."""
        ws, sch = self.ws, self.scheduler
        if ws is None or sch is None or ws.read_only or self._sched_running:
            return
        now = datetime.now(self.q.tz())
        decision = sch.decide(now)
        if not decision.run:
            return
        owners = sch.sources()
        today = now.date()
        if not owners:
            sch.mark_ran(today)
            return
        self._sched_running = True
        cs = self.checkpoints
        trigger = "startup" if (startup and decision.missed) else "scheduled"

        def work(tok):
            results = []
            for oid in owners:
                tok.check()
                try:
                    m = cs.create(oid, tr('ui.app.checkpoint_programat'), trigger=trigger, missed_note=decision.note)
                    results.append((oid, "created" if m else "unchanged", None))
                except Exception as exc:  # raportat, nu ascuns
                    results.append((oid, "failed", str(exc)))
            return results

        def done(results) -> None:
            self._sched_running = False
            ok = sum(1 for r in results if r[1] == "created")
            bad = [r for r in results if r[1] == "failed"]
            if not bad:
                sch.mark_ran(today)  # la erori nu marcam, ca sa reincerce
            msg = tr('ui.app.checkpoint_programat_create_fara_modificari_esuate', ok=ok, len_results_ok_len_bad=len(results) - ok - len(bad), len_bad=len(bad))
            self.status.set_message(msg)
            if decision.note:
                show_info(self.root, decision.note, tr('ui.app.checkpoint_programat_ratat'))
            if bad:
                show_error(self.root, tr('ui.app.checkpoint_programat_esuat_2') + "\n".join(
                    tr('ui.app.checkpoint_failure_item', ws_nodes_o_title_if_o_in_ws_nodes_else_o=ws.nodes[o].title if o in ws.nodes else o, e=e) for o, _s, e in bad[:5]), tr('ui.app.checkpoint'))

        def failed(exc: BaseException) -> None:
            self._sched_running = False
            self.status.set_message(tr('ui.app.checkpoint_programat_esuat', exc=exc))

        self._track_workspace_job(self.bridge.submit(work, done, failed, name="scheduled-checkpoint"))

    def open_code_in_explorer(self, node_id: str | None) -> None:
        if not node_id:
            return
        src = self.files.usable_source_dir(node_id)
        try:
            system_open.reveal_in_explorer(src if src else self.ws.node_dir(node_id))
        except FocusDeskError as exc:
            show_error(self.root, str(exc))

    def open_node_folder(self, node_id: str | None) -> None:
        if node_id and node_id in self.ws.nodes:
            try:
                system_open.reveal_in_explorer(self.ws.node_dir(node_id))
            except FocusDeskError as exc:
                show_error(self.root, str(exc))

    def open_code_in_vscode(self, node_id: str | None) -> None:
        if not node_id:
            return
        src = self.files.usable_source_dir(node_id)
        if src is None:
            show_error(self.root, tr('ui.app.nu_exista_un_folder_de_cod_valid_pentru_acest_nod'))
            return
        try:
            system_open.open_in_vscode(src, self.ws.settings.vscode_path)
        except FocusDeskError as exc:
            show_error(self.root, str(exc))

    def _tick(self) -> None:
        if self._tick_job:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None
        if self.ws is None or self.timer is None:
            return
        t = self.timer
        if t.recovered is None and t.state is not None:
            try:t.tick()
            except Exception as exc:
                self.status.set_save_error(str(exc))
                if t.state:t.state.state='paused'
            node = self.ws.nodes.get(t.node_id or "")
            label = tr('ui.app.timer_status', sesiune_if_t_running_else_pauza=tr('ui.tab_journal.sesiune') if t.running else tr('ui.session_ui.pauza'), node_title_if_node_else=node.title if node else '?', format_seconds_t_seconds=format_seconds(t.seconds))
            if t.state.state == "paused" and t.pending_gap:
                label += tr('ui.app.nu_a_fost_numarat_intervalul_de_repaus')
            self.status.set_timer(label, active=t.running)
        else:
            self.status.set_timer(tr('ui.session_ui.nicio_sesiune_de_lucru_pornita'))
        if self.current_view == "today":
            self.today.update_timer()
        self.update_session_buttons()
        self.timer_indicator.update_state()
        if self.current_view == "activity": self.activity_page.update_live()
        self._tick_count += 1
        if self._tick_count % 60 == 0 and self.current_view == "activity": self.activity_page.refresh()
        if self._tick_count % 30 == 0:
            self.check_scheduled_checkpoints()
        self._tick_job = self.root.after(1000, self._tick)

    def update_session_buttons(self) -> None:
        for b in self.session_buttons:
            b.update_state()
        if self.current_view == "task_space": self.task_space.update_timer()

    def _handle_timer_gap(self) -> None:
        t = self.timer
        if t is None or self._gap_dialog_open or not t.state or t.state.state != "paused" or not t.pending_gap:
            return
        self._ask_gap(t.pending_gap)

    def _ask_gap(self, gap: float) -> None:
        t = self.timer
        if t is None:
            return
        self._gap_dialog_open = True
        try:
            minutes = round(gap / 60)
            ans = ask_choice(self.root, tr('ui.app.interval_de_inactivitate'),
                             tr('ui.app.intre_doua_verificari_au_trecut_aproximativ_min_repaus_suspendare_wind', minutes=minutes),
                             [("none", tr('ui.app.nimic_0_min')), ("all", tr('ui.app.tot_min', minutes=minutes)), ("custom", tr('ui.app.alta_valoare'))])
            add = 0.0
            if ans == "all":
                add = gap
            elif ans == "custom":
                from .formats import parse_duration

                val = ask_string(self.root, tr('ui.app.timp_de_adaugat'), tr('ui.app.minute_ex_20_1h'), "0", tr('ui.tab_subtasks.adauga'))
                try:
                    mins = parse_duration(val or "0") or 0
                    add = min(mins * 60, gap)
                except ValueError as exc:
                    show_error(self.root, str(exc))
            if ans is not None:self.run_write(lambda:t.resume(count_gap_seconds=add))
        finally:
            self._gap_dialog_open = False

    def _handle_recovered_timer(self):
        t=self.timer
        if not t or not t.recovered or self.ws.read_only or getattr(self,'_recovering_session',False):return
        self._recovering_session=True
        try:
            rec=t.recovered;st=t.state
            if st.finalization:
                if confirm(self.root,tr('ui.app.incheierea_sesiunii_a_fost_intrerupta_reiau_salvarea_fara_a_adauga_tim')):
                    self.run_write(t.stop)
                return
            ans=ask_choice(self.root,tr('ui.app.sesiune_de_recuperat'),
                tr('ui.app.task_ultima_stare_ultima_salvare_lucrat_salvat_timpul_cat_aplicatia_a', rec_node_title=rec.node_title, in_pauza_if_st_state_paused_else_in_lucru=tr('ui.session_ui.in_pauza') if st.state=='paused' else tr('ui.session_ui.in_lucru'), st_heartbeat_at_astimezone_self_q_tz=st.heartbeat_at.astimezone(self.q.tz()), format_seconds_t_seconds=format_seconds(t.seconds)),
                [('continue',tr('ui.session_ui.continua')),('end',tr('ui.app.incheie_la_o_ora_aleasa')),('discard',tr('ui.app.renunta_la_intervalul_nesalvat'))])
            if ans=='continue':self.run_write(t.continue_recovered)
            elif ans=='end':
                from .session_ui import parse_local_stamp
                value=ask_string(self.root,tr('ui.app.ora_incheierii'),tr('ui.app.data_si_ora_efectiva_iso_cu_offset_pentru_dst'),
                    st.heartbeat_at.astimezone(self.q.tz()).isoformat(timespec='seconds'),tr('ui.session_ui.incheie'))
                if value:
                    try:stamp=parse_local_stamp(value,self.ws.settings.timezone)
                    except ValueError as exc:show_error(self.root,str(exc));return
                    self.run_write(lambda:t.finalize_recovered(t.seconds,stopped_at=stamp))
            elif ans=='discard':
                # Saved heartbeat work is preserved; only the unknown/offline interval is discarded.
                self.run_write(lambda:t.finalize_recovered(t.seconds,stopped_at=st.heartbeat_at))
            self.refresh_all();self.timer_indicator.update_state()
        finally:self._recovering_session=False


class StartSessionDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: FocusDeskApp, node: Node, src_dir: Path | None, n_files: int) -> None:
        super().__init__(parent, tr('ui.app.incepe_sesiune'), ok_text=tr('ui.app.incepe'))
        defaults = app.config.session_open
        ttk.Label(self.body, text=node.title, style="Section.TLabel", wraplength=420).pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", text=tr('ui.app.alege_ce_sa_se_deschida_acum_doar_la_cerere')).pack(
            anchor="w", pady=(2, 8))
        self.vars = {
            "vscode": tk.BooleanVar(value=defaults.get("vscode", False)),
            "explorer": tk.BooleanVar(value=defaults.get("explorer", False)),
            "files": tk.BooleanVar(value=defaults.get("files", False)),
        }
        if src_dir is not None:
            ttk.Checkbutton(self.body, variable=self.vars["vscode"],
                            text=tr('ui.app.folderul_de_cod_in_vs_code', src_dir=src_dir)).pack(anchor="w", pady=2)
        ttk.Checkbutton(self.body, variable=self.vars["explorer"],
                        text=tr('ui.app.folderul_in_explorer') + (tr('common.code_suffix') if src_dir else tr('common.node_suffix'))).pack(anchor="w", pady=2)
        if n_files:
            ttk.Checkbutton(self.body, variable=self.vars["files"],
                            text=tr('ui.app.fisierele_atasate_scripturile_nu_se_deschid', n_files=n_files)).pack(anchor="w", pady=2)

    def collect(self) -> dict[str, bool]:
        return {k: v.get() for k, v in self.vars.items()}


class StopSessionDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: FocusDeskApp, node: Node | None, seconds: float) -> None:
        super().__init__(parent, tr('ui.app.opreste_sesiunea'), resizable=True, ok_text=tr('ui.app.salveaza_si_opreste'))
        from ..domain.labels import STATUS_LABELS
        from .formats import duration_to_text

        self.app = app
        self.node = node
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text=node.title if node else tr('common.task_placeholder'), style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(b, text=tr('ui.app.timp_lucrat_efectiv_timpul_planificat_nu_se_numara', format_seconds_seconds=format_seconds(seconds)),
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(b, text=tr('ui.app.ce_am_facut')).grid(row=2, column=0, sticky="nw", pady=3)
        self.text = tk.Text(b, height=5, width=52, wrap="word", font="TkTextFont")
        self.text.grid(row=2, column=1, sticky="ew", pady=3)
        self.text.focus_set()
        ttk.Label(b, text=tr('ui.tab_details.urmatorul_pas')).grid(row=3, column=0, sticky="w", pady=3)
        self.next_var = tk.StringVar(value=(node.next_action or "") if node else "")
        ttk.Entry(b, textvariable=self.next_var).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Label(b, text=tr('ui.planning.timp_ramas')).grid(row=4, column=0, sticky="w", pady=3)
        rem = node.remaining_minutes if node and node.remaining_minutes is not None else (
            node.estimated_minutes if node else None)
        self.rem_var = tk.StringVar(value=duration_to_text(rem))
        ttk.Entry(b, textvariable=self.rem_var, width=12).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(b, text=tr('ui.tab_details.status')).grid(row=5, column=0, sticky="w", pady=3)
        self.status_var = tk.StringVar(value="(neschimbat)")
        opts = ["(neschimbat)", STATUS_LABELS[Status.IN_PROGRESS], STATUS_LABELS[Status.WAITING],
                STATUS_LABELS[Status.TESTING], STATUS_LABELS[Status.DONE]]
        ttk.Combobox(b, textvariable=self.status_var, values=opts, state="readonly").grid(
            row=5, column=1, sticky="w", pady=3)
        self._rem_original = rem

    def validate(self) -> bool:
        from .formats import parse_duration

        try:
            parse_duration(self.rem_var.get())
        except ValueError as exc:
            show_error(self, str(exc))
            return False
        return True

    def collect(self) -> dict:
        from ..domain.labels import STATUS_FROM_LABEL
        from .formats import parse_duration

        rem = parse_duration(self.rem_var.get())
        status_label = self.status_var.get()
        new_status = STATUS_FROM_LABEL.get(status_label)
        return {
            "summary": self.text.get("1.0", "end").strip(),
            "next_action": self.next_var.get(),
            "remaining_minutes": rem,
            "keep_remaining": rem == self._rem_original,
            "new_status": new_status,
        }
