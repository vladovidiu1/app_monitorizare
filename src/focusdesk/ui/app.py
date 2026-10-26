"""Fereastra principala FocusDesk."""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

import ttkbootstrap as tb

from .. import __version__
from ..config import AppConfig, resource_path
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
from .calendar_page import CalendarPage, PlanTab
from .ai_ui import AiController, AiWindow
from .assistant_ui import AssistantTab, AssistantWindow
from .mail_monitor_ui import MailReviewPage, MailWatchController
from .common import (
    ModalDialog, THEMES, SessionButton, ask_choice, ask_string, apply_theme, confirm, show_error, show_info,
)
from .dashboard import DashboardWindow
from .dialogs import IssuesDialog, MoveDialog, NewNodeDialog, NodePickerDialog, TrashDialog
from .inspector import Inspector
from .mail_ui import MailDialog
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

log = logging.getLogger(__name__)

VIEW_TITLES = {
    "today": "Astăzi", "inbox": "Inbox", "waiting": "În așteptare", "overdue": "Restante",
    "calendar": "Calendar", "archive": "Arhivă",
    "mail_review": "Mailuri de analizat",
}
VIEW_HINTS = {
    "inbox": "Inbox-ul este gol. Captează rapid cu Ctrl+N.",
    "waiting": "Nimic în așteptare.",
    "overdue": "Nicio întârziere.",
    "archive": "Nimic arhivat.",
}


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
        self.ai = AiController(self)
        self.ai_window = None
        self.assistant_window = None
        self.mail_watch = MailWatchController(self)
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
        self.calendar_provider = LocalOnlyProvider()
        self._busy = 0
        self.current_view = "today"
        self.current_scope: str | None = None
        self.selected_id: str | None = None
        self._refresh_pending = False
        self._search_job = None
        self._gap_dialog_open = False
        self._tick_job = None
        self._initial_path = workspace_path
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
        from .design import icon, button
        ttk.Label(top, text="  FocusDesk", image=icon(top,"brand",24), compound="left", style="Brand.TLabel").pack(side="left")
        self.ws_label = ttk.Label(top, text="", style="Muted.TLabel", width=21)
        self.ws_label.pack(side="left", padx=(12, 0), pady=(3, 0))
        self.new_btn = tb.Menubutton(top, text="+ Nou", bootstyle="primary")
        self.new_menu = tk.Menu(self.new_btn, tearoff=False)
        self.new_menu.add_command(label="Task\tCtrl+N", command=lambda: self.new_node(Kind.TASK))
        self.new_menu.add_command(label="Subtask în selecția curentă", command=self.new_subtask)
        self.new_menu.add_separator()
        self.new_menu.add_command(label="Folder / categorie", command=lambda: self.new_node(Kind.FOLDER))
        self.new_menu.add_command(label="Proiect", command=lambda: self.new_node(Kind.PROJECT))
        self.new_btn["menu"] = self.new_menu
        self.new_btn.pack(side="right")
        self.mail_btn = tb.Button(top, text="E-mail", image=icon(top,"mail"), compound="left", command=self.compose_mail,
                                  bootstyle="secondary-outline")
        self.mail_btn.pack(side="right", padx=(0, 8))
        self.assistant_btn = button(top, "Asistent", self.open_assistant, glyph="assistant")
        self.assistant_btn.pack(side="right", padx=(0, 8))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=34)
        self.search_entry.pack(side="right", fill="x", expand=True, padx=(0, 16))
        ttk.Label(top, text="", image=icon(top,"search"), style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self.search_var.trace_add("write", lambda *_: self._debounce_search())
        self.search_entry.bind("<Escape>", lambda _e: self._clear_search())
        self.search_entry.bind("<Return>", lambda _e: self._run_search())

        self.ai_state = ttk.Label(self.root, text="AI local · dezactivat", style="Muted.TLabel", padding=(18,0,12,6))
        self.ai_state.pack(fill="x")
        self.status = StatusBar(self.root)
        self.status.pack(side="bottom", fill="x")
        ttk.Separator(self.root).pack(side="bottom", fill="x")

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
        self.mail_page = MailReviewPage(self.center, self)
        self.inspector.add_tab(DetailsTab(self.inspector.nb, self))
        self.inspector.add_tab(SubtasksTab(self.inspector.nb, self))
        self.inspector.add_tab(PlanTab(self.inspector.nb, self))
        self.inspector.add_tab(FilesTab(self.inspector.nb, self))
        self.inspector.add_tab(JournalTab(self.inspector.nb, self))
        self.inspector.add_tab(VersionsTab(self.inspector.nb, self))
        self.inspector.add_tab(AssistantTab(self.inspector.nb, self))
        self.root.after(80, self._apply_sashes)

    def _apply_sashes(self, attempt: int = 0) -> None:
        try:
            self.root.update_idletasks()
            total = self.paned.winfo_width()
            if total < 600 and attempt < 10:
                self.root.after(100, lambda: self._apply_sashes(attempt + 1))
                return
            panes = self.paned.panes()
            from .design import px
            left = self.config.sash_left or px(self.root,220)
            right = self.config.sash_right or px(self.root,440)
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
        m.add_cascade(label="Fișier", menu=f, underline=0)
        f.add_command(label="Deschide workspace…", command=self.menu_open_workspace)
        f.add_command(label="Workspace nou…", command=self.menu_new_workspace)
        f.add_command(label="Creează workspace demonstrativ…", command=self.menu_demo_workspace)
        self.recent_menu = tk.Menu(f, tearoff=False)
        f.add_cascade(label="Workspace-uri recente", menu=self.recent_menu)
        f.add_separator()
        f.add_command(label="Salvează\tCtrl+S", command=self.save_current)
        f.add_command(label="Rescanează workspace", command=self.rescan)
        f.add_separator()
        f.add_command(label="Backup acum (metadate)", command=lambda: self.backup_now(False))
        f.add_command(label="Backup acum (complet, cu fișiere)", command=lambda: self.backup_now(True))
        f.add_command(label="Restaurează backup într-un folder nou…", command=self.restore_backup)
        f.add_separator()
        f.add_command(label="Coș…", command=self.open_trash)
        f.add_separator()
        f.add_command(label="Ieșire", command=self.on_close)
        self.file_menu = f
        # Organizare
        o = tk.Menu(m, tearoff=False)
        m.add_cascade(label="Organizare", menu=o, underline=0)
        o.add_command(label="Task nou\tCtrl+N", command=lambda: self.new_node(Kind.TASK))
        o.add_command(label="Subtask nou", command=self.new_subtask)
        o.add_command(label="Folder nou", command=lambda: self.new_node(Kind.FOLDER))
        o.add_command(label="Proiect nou", command=lambda: self.new_node(Kind.PROJECT))
        o.add_separator()
        o.add_command(label="Redenumește\tF2", command=self.rename_selected)
        o.add_command(label="Mută…", command=self.move_selected)
        o.add_command(label="Face subtask al task-ului de deasupra\tAlt+→", command=self.indent_selected)
        o.add_command(label="Scoate un nivel\tAlt+←", command=self.outdent_selected)
        o.add_command(label="Adaugă legătură…", command=self.link_selected)
        o.add_command(label="Prioritate pentru azi (comută)", command=self.toggle_pin_selected)
        o.add_command(label="Finalizează / redeschide", command=self.toggle_done_selected)
        o.add_separator()
        o.add_command(label="Arhivează / dezarhivează", command=self.toggle_archive_selected)
        o.add_command(label="Trimite în coș", command=self.trash_selected)
        o.add_separator()
        o.add_command(label="Programează sesiune…", command=lambda: self.schedule_session())
        o.add_command(label="Planificare asistată…", command=self.open_planner)
        o.add_command(label="Task-uri recurente…", command=self.open_recurrences)
        o.add_command(label="Trimite e-mail din task…\tCtrl+M", command=self.compose_mail)
        o.add_separator()
        self.session_menu = tk.Menu(o, tearoff=False)
        self.session_menu.add_command(label="Începe sesiune pentru selecție", command=self.start_selected_session)
        self.session_menu.add_command(label="Pauză / continuă", command=self.toggle_pause)
        self.session_menu.add_command(label="Oprește sesiunea…", command=self.stop_session)
        o.add_cascade(label="Sesiune de lucru", menu=self.session_menu)
        self.org_menu = o
        # Instrumente
        t = tk.Menu(m, tearoff=False)
        m.add_cascade(label="Instrumente", menu=t, underline=0)
        self.dark_var = tk.BooleanVar(value=self.config.theme == "dark")
        t.add_command(label="Aspect luminos FocusDesk", command=self.toggle_theme)
        self.inspector_var = tk.BooleanVar(value=self.config.show_inspector)
        t.add_checkbutton(label="Arată inspectorul", variable=self.inspector_var, command=self.toggle_inspector)
        self.archived_var = tk.BooleanVar(value=self.config.show_archived)
        t.add_checkbutton(label="Arată elementele arhivate în arbore", variable=self.archived_var,
                          command=self.toggle_archived)
        t.add_separator()
        t.add_command(label="Dashboard timp lucrat\tCtrl+D", command=self.open_dashboard)
        t.add_command(label="Asistent…", command=self.open_assistant)
        t.add_command(label="AI local — propuneri…", command=self.open_ai)
        t.add_separator()
        t.add_command(label="Verificare integritate workspace…", command=self.show_issues)
        t.add_command(label="Setări…", command=self.open_settings)
        self.tools_menu = t
        # Ajutor
        h = tk.Menu(m, tearoff=False)
        m.add_cascade(label="Ajutor", menu=h, underline=0)
        h.add_command(label="Scurtături de tastatură", command=self.show_shortcuts)
        h.add_command(label="Despre FocusDesk", command=self.show_about)

    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<Control-n>", lambda _e: self.new_node(Kind.TASK))
        r.bind("<Control-f>", lambda _e: (self.search_entry.focus_set(), self.search_entry.select_range(0, "end")))
        r.bind("<Control-s>", lambda _e: self.save_current())
        r.bind("<F2>", lambda _e: self.rename_selected())
        r.bind("<F5>", lambda _e: self.refresh_all())
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
        choice = ask_choice(self.root, "Bun venit în FocusDesk",
                            "Alege unde ții datele. Workspace-ul este un folder local (JSON + Markdown), "
                            "independent de aplicație și de orice cont cloud.",
                            [("new", "Workspace nou…"), ("open", "Deschide existent…"),
                             ("demo", "Workspace demonstrativ…"), ("quit", "Ieșire")])
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
            show_error(self.root, f"Workspace-ul nu a putut fi deschis: {exc}")
            return False
        if ws.repo.lock_conflict:
            ans = ask_choice(self.root, "Workspace deja deschis",
                             "Workspace-ul este deschis într-o altă instanță FocusDesk. Poți continua doar pentru "
                             "citire; editarea este blocată ca să nu se suprascrie datele.",
                             [("ro", "Deschide doar pentru citire"), ("cancel", "Renunță")])
            if ans != "ro":
                ws.close()
                return False
        self._attach(ws, path)
        return True

    def _attach(self, ws: Workspace, path: Path) -> None:
        self.ws = ws
        self.q = Queries(ws)
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
        self.root.title(f"FocusDesk — {ws.name}" + ("  [doar citire]" if ws.read_only else ""))
        self.ws_label.configure(text=ws.name)
        self.status.set_workspace(ws.name, str(path), ws.read_only)
        self.status.set_saved() if not ws.read_only else self.status.set_save_idle("Doar citire")
        self.status.set_calendar("Calendar: local")
        self._rebuild_recent_menu()
        self.outlook.attach()
        self.sidebar._first_fill = True
        self.selected_id = None
        self.after_workspace_attached()
        self.show_view("today", select_sidebar=True)
        self.sidebar.refresh()
        self.root.after(200, self._post_open_checks)
        self._tick()

    def after_workspace_attached(self) -> None:
        """Punct de extindere pentru etapele ulterioare."""
        if not self.ws.read_only:
            from ..services.mail_analysis import reconcile
            reconcile(self.ws)
        self.mail_watch.next_due = 0

    def _post_open_checks(self) -> None:
        ws = self.ws
        if ws is None:
            return
        errors = [i for i in ws.issues if i.severity == "error"]
        if ws.recovery_messages or errors:
            IssuesDialog(self.root, ws).run()
        if self.timer and self.timer.recovered:
            self._handle_recovered_timer()
        if not ws.read_only:
            self._maintenance_on_open()
            self.root.after(3000, lambda: self.check_scheduled_checkpoints(startup=True))
        if not ws.read_only and ws.settings.backup.daily:
            self.bridge.submit(lambda tok: backup_service.ensure_daily_backup(ws),
                               on_done=lambda r: self.status.set_message(
                                   f"Backup zilnic creat ({r.kind})" if r else ""),
                               on_error=lambda e: self.status.set_message(f"Backup zilnic eșuat: {e}"),
                               name="daily-backup")

    def _maintenance_on_open(self) -> None:
        """Sesiuni ratate, instante recurente de azi si zilele ratate (de ales de utilizator)."""
        ws = self.ws
        missed_sessions = 0
        try:
            missed_sessions = self.sessions.mark_missed()
            created, missed = self.recurrence.generate_today_all()
        except FocusDeskError as exc:
            self.status.set_message(f"Întreținere la pornire: {exc}")
            return
        msgs = []
        if missed_sessions:
            msgs.append(f"{missed_sessions} sesiuni planificate au fost marcate ca ratate")
        if created:
            msgs.append(f"{len(created)} task-uri recurente create pentru azi")
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
        if not self.confirm_leave():
            return False
        if self.timer and self.timer.active:
            ans = ask_choice(self.root, "Sesiune activă",
                             "Este o sesiune de lucru activă. Ce faci cu ea înainte de a schimba workspace-ul?",
                             [("stop", "Oprește sesiunea"), ("keep", "Las-o (se reconciliază la redeschidere)"),
                              ("cancel", "Anulează")])
            if ans == "stop":
                if not self.stop_session():
                    return False
            elif ans != "keep":
                return False
        self.ai.invalidate_workspace()
        self.mail_watch.invalidate(clear_selection=True)
        if self.ai_window:
            self.ai_window.destroy()
        self.ai.cancel()
        self.ws.close()
        self.ws = None  # type: ignore[assignment]
        self.q = None  # type: ignore[assignment]
        self.timer = None
        return True

    def on_close(self) -> None:
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
        self.ai.close()
        self.bridge.close()
        for pending in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", pending)
        self.root.destroy()

    # ================================================================
    # Events / refresh
    # ================================================================
    def _on_ws_event(self, event: str, data: dict) -> None:
        if event == "mail_changed":
            if self.current_view == "mail_review":
                self.mail_page.refresh()
            return
        if event == "settings_changed":
            self.mail_watch.invalidate()
        if event in ("node_created", "node_updated", "node_moved", "node_trashed", "node_restored", "reloaded",
                     "sessions_changed", "trash_changed"):
            self._schedule_refresh()
        elif event == "timer_gap":
            self.root.after(0, self._handle_timer_gap)

    def _schedule_refresh(self) -> None:
        if not self._refresh_pending:
            self._refresh_pending = True
            self.root.after_idle(self._do_scheduled_refresh)

    def _do_scheduled_refresh(self) -> None:
        self._refresh_pending = False
        self.refresh_all()

    def refresh_all(self) -> None:
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
        if v == "today":
            self._show_center(self.today)
            self.today.refresh()
        elif v == "calendar":
            self._show_calendar()
        elif v == "mail_review":
            self._show_center(self.mail_page)
            self.mail_page.refresh()
        else:
            self._show_center(self.tasklist)
            self._configure_list()

    def _show_center(self, widget: tk.Misc) -> None:
        for w in (self.tasklist, self.today, self.calendar_page, self.mail_page):
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
            self.tasklist.set_source(f"Rezultate pentru „{query}”", lambda: q.search(query), "Căutare globală",
                                     show_closed=True, empty_hint="Niciun rezultat.")
        elif v.startswith("tree:"):
            nid = self.current_scope
            node = ws.get(nid) if nid else None
            if node is None:
                return
            self.tasklist.set_source(node.title, lambda: q.tasks_in(nid), ws.breadcrumb(nid),
                                     empty_hint="Niciun task aici. Scrie un titlu mai sus și apăsă Enter.",
                                     scope_id=nid)
        else:
            loaders = {"inbox": q.view_inbox, "waiting": q.view_waiting, "overdue": q.view_overdue,
                       "archive": q.view_archive}
            self.tasklist.set_source(VIEW_TITLES.get(v, v), loaders[v], "Vizualizare inteligentă",
                                     show_closed=(v == "archive"), empty_hint=VIEW_HINTS.get(v, ""))

    # ================================================================
    # Navigation
    # ================================================================
    def confirm_leave(self) -> bool:
        if self.ws is None or not self.inspector.is_dirty():
            return True
        ans = ask_choice(self.root, "Modificări nesalvate",
                         "Ai modificări nesalvate în inspector.",
                         [("save", "Salvează"), ("discard", "Renunță la modificări"), ("cancel", "Rămâi aici")])
        if ans == "save":
            return self.inspector.save()
        if ans == "discard":
            self.inspector.revert()
            return True
        return False

    def show_view(self, key: str, select_sidebar: bool = False) -> None:
        if self.ws is None:
            return
        if not self.confirm_leave():
            self._restore_selection_widgets()
            return
        self.current_view = key
        self.current_scope = None
        if key in VIEW_TITLES:
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
        self.current_view = f"tree:{node_id}"
        self.current_scope = node_id
        self.selected_id = node_id
        self.inspector.load(node_id)
        self._show_center(self.tasklist)
        self._configure_list()
        self.tasklist.clear_selection()

    def select_node(self, node_id: str, source: str = "program", reveal: bool = False) -> None:
        if self.ws is None or node_id not in self.ws.nodes:
            return
        if node_id == self.selected_id and source == "list":
            return
        if not self.confirm_leave():
            self._restore_selection_widgets()
            return
        if reveal:
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
        self.inspector.load(node_id)
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
        tab = self.inspector.tab_by_title("Detalii")
        if tab is not None and hasattr(tab, "title_entry"):
            tab.title_entry.focus_set()  # type: ignore[attr-defined]

    def after_inspector_save(self, node_id: str) -> None:
        self.sidebar.refresh()
        self.tasklist.refresh() if self.tasklist.winfo_ismapped() else None
        if self.today.winfo_ismapped():
            self.today.refresh()

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
                self.show_view("today", select_sidebar=True)
            return
        if self.current_view != f"search:{text}":
            if not self.confirm_leave():
                return
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
    def run_write(self, fn: Callable[[], Any], *, success_text: str = "Salvat", refresh: bool = False) -> bool:
        if self.ws is None:
            return False
        try:
            fn()
        except ExternalModificationError as exc:
            self.status.set_save_error("Conflict: modificat extern")
            self._handle_external_modification(str(exc))
            return False
        except ReadOnlyError:
            show_error(self.root, "Workspace-ul este deschis doar pentru citire.")
            return False
        except FocusDeskError as exc:
            self.status.set_save_error("Eroare la salvare")
            show_error(self.root, str(exc))
            return False
        except Exception as exc:
            log.exception("Eroare neașteptată la scriere")
            self.status.set_save_error("Eroare la salvare")
            show_error(self.root, f"Eroare neașteptată: {exc}")
            return False
        self.status.set_saved()
        if refresh:
            self.refresh_all()
        return True

    def _handle_external_modification(self, message: str) -> None:
        ans = ask_choice(self.root, "Fișier modificat extern",
                         f"{message}\n\nAplicația nu suprascrie silențios modificările făcute din afară. "
                         "Reîncarc workspace-ul de pe disc? (modificările nesalvate din formular se pierd)",
                         [("reload", "Reîncarcă de pe disc"), ("cancel", "Anulează")])
        if ans == "reload" and self.ws:
            self.ws.reload()
            self.refresh_all()

    def save_current(self) -> None:
        if self.ws is None:
            return
        if self.inspector.is_dirty():
            self.inspector.save()
        else:
            self.status.set_message("Nimic de salvat — modificările se scriu imediat pe disc.")

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
            show_error(self.root, "Workspace-ul este deschis doar pentru citire.")
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

    def new_subtask(self) -> None:
        nid = self.selected_id
        if not nid or self.ws is None or self.ws.nodes[nid].kind != Kind.TASK:
            show_info(self.root, "Selectează întâi un task pentru a-i adăuga un subtask.")
            return
        self.new_node(Kind.TASK, parent_id=nid)

    def quick_add_task(self, parent_id: str, title: str) -> bool:
        """Task rapid (doar titlu) sub un container sau un alt task; la orice adancime."""
        if self.ws is None or parent_id not in self.ws.nodes:
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
            show_info(self.root, "Task-ul trebuie să aibă deasupra lui (pe același nivel) un alt task "
                      "căruia să îi devină subtask.")
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
            show_info(self.root, "Task-ul este deja la primul nivel al containerului său.")
            return
        if self.run_write(lambda: self.ws.move(node.id, parent.parent_id, parent.sort_order + 5), refresh=True):
            self.tasklist.select(node.id)

    def compose_mail(self, node_id: str | None = None, *, ai_draft=None, standalone=False) -> None:
        """E-mail din task prin Outlook Classic; trimiterea porneste doar din dialog, dupa confirmare."""
        if self.ws is None:
            return
        nid = node_id or self.selected_id
        node = self.ws.nodes.get(nid) if nid and not standalone else None
        if node is None and ai_draft is None:
            show_info(self.root, "Selectează un task din care să trimiți e-mailul.")
            return
        dialog = MailDialog(self.root, self, node)
        if ai_draft is not None:
            dialog.subject_var.set(ai_draft.subject)
            dialog.text.delete("1.0", "end")
            dialog.text.insert("1.0", ai_draft.body)
        res = dialog.run()
        if not res:
            return
        draft, send = res["draft"], res["action"] == "send"

        def done(_result: str) -> None:
            if not send:
                self.status.set_message("Ciorna este deschisă în Outlook")
                return
            self.status.set_message(f"E-mail trimis către {', '.join(draft.to)}")
            recorded = False
            if node is not None and not self.ws.read_only and node.id in self.ws.nodes:
                recorded = self.run_write(lambda: self.ws.add_note(node.id, journal_text(draft), kind="action"))
                self.inspector.refresh_current()
            suffix = "\n\nTrimiterea este notată în Jurnalul taskului." if recorded else ""
            show_info(self.root, f"E-mail trimis către:\n{', '.join(draft.to)}{suffix}",
                      "E-mail trimis")

        self.outlook.send_mail(draft, send, done)

    def _selected_node(self) -> Node | None:
        if self.ws is None or not self.selected_id:
            return None
        return self.ws.nodes.get(self.selected_id)

    def rename_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        title = ask_string(self.root, "Redenumește", "Titlu nou (directorul fizic și UUID-ul rămân neschimbate):",
                           node.title, "Redenumește")
        if title and title != node.title:
            if self.run_write(lambda: self.ws.rename(node.id, title), refresh=True):
                self.inspector.load(node.id)

    def move_selected(self) -> None:
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
        picked = NodePickerDialog(self.root, self.ws, "Legătură către…", exclude={node.id, *node.related_node_ids}).run()
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
        node = self._selected_node()
        if node is None or node.kind == Kind.FOLDER:
            return
        new = Status.TODO if node.status in CLOSED_STATUSES else Status.DONE
        if new == Status.DONE and self.ws.future_sessions(node.id):
            ans = ask_choice(self.root, "Sesiuni viitoare",
                             "Task-ul are sesiuni planificate în viitor. Le anulez?",
                             [("cancel", "Anulează sesiunile"), ("keep", "Păstrează-le"), ("abort", "Nu finaliza")])
            if ans in (None, "abort"):
                return
            if ans == "cancel":
                self.run_write(lambda: self.ws.cancel_sessions(self.ws.future_sessions(node.id)))
        self.run_write(lambda: self.ws.update_node(node.id, status=new), refresh=True)

    def toggle_archive_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        if node.archived_at is not None:
            self.run_write(lambda: self.ws.unarchive(node.id), refresh=True)
            return
        policy = "keep"
        if self.ws.future_sessions(node.id):
            ans = ask_choice(self.root, "Sesiuni viitoare",
                             "Nodul are sesiuni planificate în viitor. Ce faci cu ele?",
                             [("keep", "Păstrează-le"), ("cancel", "Anulează-le"), ("abort", "Nu arhiva")])
            if ans in (None, "abort"):
                return
            policy = ans
        self.run_write(lambda: self.ws.archive(node.id, future_sessions=policy), refresh=True)

    def trash_selected(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        n = len(self.ws.subtree_ids(node.id))
        extra = f" și {n - 1} descendenți" if n > 1 else ""
        if confirm(self.root, f"Muți „{node.title}”{extra} în coș? Poți restaura din Fișier › Coș."):
            if self.run_write(lambda: self.ws.trash(node.id), refresh=True):
                self.selected_id = None
                self.inspector.load(None)

    # ---- context menu -----------------------------------------------
    def popup_context_menu(self, x: int, y: int, node_id: str | None) -> None:
        if self.ws is None:
            return
        node = self.ws.nodes.get(node_id) if node_id else None
        if node is not None:
            self.selected_id = node.id
            self.inspector.load(node.id)
        menu = tk.Menu(self.root, tearoff=False)
        ro = self.ws.read_only
        state = "disabled" if ro else "normal"
        if node is None:
            menu.add_command(label="Task nou", command=lambda: self.new_node(Kind.TASK, parent_id=None), state=state)
            menu.add_command(label="Folder nou", command=lambda: self.new_node(Kind.FOLDER, parent_id=None), state=state)
            menu.add_command(label="Proiect nou", command=lambda: self.new_node(Kind.PROJECT, parent_id=None), state=state)
        else:
            if node.kind == Kind.TASK:
                menu.add_command(label="Subtask nou", command=lambda: self.new_node(Kind.TASK, parent_id=node.id),
                                 state=state)
                if self.timer_active():
                    menu.add_command(label="■ Oprește sesiunea", command=self.stop_session)
                else:
                    menu.add_command(label="▶ Începe sesiune", command=lambda: self.start_session(node.id),
                                     state=state)
                menu.add_command(label="Finalizează / redeschide", command=self.toggle_done_selected, state=state)
                menu.add_command(label="Prioritate pentru azi (comută)", command=self.toggle_pin_selected, state=state)
            else:
                menu.add_command(label="Task nou aici", command=lambda: self.new_node(Kind.TASK, parent_id=node.id),
                                 state=state)
                menu.add_command(label="Folder nou aici", command=lambda: self.new_node(Kind.FOLDER, parent_id=node.id),
                                 state=state)
                if node.kind == Kind.FOLDER:
                    menu.add_command(label="Proiect nou aici",
                                     command=lambda: self.new_node(Kind.PROJECT, parent_id=node.id), state=state)
            menu.add_separator()
            menu.add_command(label="Redenumește\tF2", command=self.rename_selected, state=state)
            menu.add_command(label="Mută…", command=self.move_selected, state=state)
            if node.kind == Kind.TASK:
                menu.add_command(label="Face subtask al celui de deasupra\tAlt+→", command=self.indent_selected,
                                 state=state)
                menu.add_command(label="Scoate un nivel\tAlt+←", command=self.outdent_selected, state=state)
            menu.add_command(label="Adaugă legătură…", command=self.link_selected, state=state)
            menu.add_command(label="Trimite e-mail…\tCtrl+M", command=lambda: self.compose_mail(node.id))
            self._extend_context_menu(menu, node)
            menu.add_separator()
            menu.add_command(label="Dezarhivează" if node.archived_at else "Arhivează",
                             command=self.toggle_archive_selected, state=state)
            menu.add_command(label="Trimite în coș", command=self.trash_selected, state=state)
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _extend_context_menu(self, menu: tk.Menu, node: Node) -> None:
        menu.add_separator()
        menu.add_command(label="Deschide folderul nodului", command=lambda: self.open_node_folder(node.id))
        if node.kind != Kind.FOLDER and self.files.usable_source_dir(node.id) is not None:
            menu.add_command(label="Deschide codul în VS Code", command=lambda: self.open_code_in_vscode(node.id))

    # ================================================================
    # Workspace / file menu
    # ================================================================
    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.delete(0, "end")
        for p in self.config.recent_workspaces:
            self.recent_menu.add_command(label=p, command=lambda p=p: self.open_workspace(Path(p)))
        if not self.config.recent_workspaces:
            self.recent_menu.add_command(label="(niciunul)", state="disabled")

    def menu_open_workspace(self) -> bool:
        d = filedialog.askdirectory(parent=self.root, title="Alege folderul workspace-ului",
                                    initialdir=self.config.last_workspace or str(Path.home()))
        if not d:
            return False
        p = Path(d)
        if not (p / "workspace.json").is_file():
            show_error(self.root, "Folderul ales nu conține un workspace FocusDesk (lipsește workspace.json).")
            return False
        return self.open_workspace(p)

    def menu_new_workspace(self) -> bool:
        d = filedialog.askdirectory(parent=self.root, title="Alege folderul în care se creează workspace-ul",
                                    initialdir=str(Path.home() / "Documents"))
        if not d:
            return False
        p = Path(d)
        if (p / "workspace.json").is_file():
            return self.open_workspace(p)
        if p.exists() and any(p.iterdir()):
            p = p / "FocusDeskData"
            if p.exists() and any(p.iterdir()):
                show_error(self.root, f"{p} există deja și nu este gol.")
                return False
            if not confirm(self.root, f"Folderul ales nu este gol. Creez workspace-ul în:\n{p} ?"):
                return False
        name = ask_string(self.root, "Workspace nou", "Nume afișat:", "FocusDesk", "Creează") or "FocusDesk"
        return self.open_workspace(p, create=True, name=name)

    def menu_demo_workspace(self) -> bool:
        from ..services.demo import create_demo_workspace

        d = filedialog.askdirectory(parent=self.root, title="Alege un folder GOL pentru workspace-ul demonstrativ",
                                    initialdir=str(Path.home() / "Documents"))
        if not d:
            return False
        p = Path(d)
        if p.exists() and any(p.iterdir()):
            p = p / "FocusDeskDemo"
            if p.exists() and any(p.iterdir()):
                show_error(self.root, f"{p} există deja și nu este gol.")
                return False
        if not self._release_current():
            return False
        try:
            create_demo_workspace(p)
        except FocusDeskError as exc:
            show_error(self.root, str(exc))
            return False
        return self.open_workspace(p)

    def rescan(self) -> None:
        if self.ws is None or not self.confirm_leave():
            return
        self.ws.reload()
        self.refresh_all()
        errors = sum(1 for i in self.ws.issues if i.severity == "error")
        warns = len(self.ws.issues) - errors
        self.status.set_message(f"Rescanat: {len(self.ws.nodes)} noduri, {errors} erori, {warns} avertismente")
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
            show_error(self.root, "Backup-ul necesită un workspace editabil.")
            return
        self.status.set_message("Se creează backup-ul…")

        def done(res) -> None:
            msg = f"Backup {'complet' if full else 'de metadate'} creat:\n{res.path}\n({res.file_count} fișiere)"
            msg += "\n\nAtenție: un backup pe același disc nu protejează de defectarea discului."
            if res.external_copy:
                msg += f"\nCopie externă: {res.external_copy}"
            if res.external_error:
                msg += f"\nCopia externă a eșuat: {res.external_error}"
            self.status.set_message("Backup creat")
            show_info(self.root, msg, "Backup")

        self.bridge.submit(lambda tok: backup_service.create_backup(ws, full=full), on_done=done,
                           on_error=lambda e: (self.status.set_message(""), show_error(self.root, str(e))),
                           name="backup")

    def restore_backup(self) -> None:
        zp = filedialog.askopenfilename(parent=self.root, title="Alege arhiva de backup",
                                        filetypes=[("Backup FocusDesk", "*.zip")])
        if not zp:
            return
        d = filedialog.askdirectory(parent=self.root, title="Alege un folder GOL pentru restaurare")
        if not d:
            return
        try:
            out = backup_service.restore_backup_to_folder(Path(zp), Path(d))
        except FocusDeskError as exc:
            show_error(self.root, str(exc))
            return
        if confirm(self.root, f"Backup restaurat în:\n{out}\n\nÎl deschid acum ca workspace?"):
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
            self.inspector.tab_by_title("Detalii").sf.sync_background()  # type: ignore[union-attr]

    def toggle_inspector(self) -> None:
        self.config.show_inspector = self.inspector_var.get()
        if self.config.show_inspector:
            if str(self.inspector) not in self.paned.panes():
                self.paned.add(self.inspector, weight=0)
                self.root.after(50, self._apply_sashes)
        else:
            if str(self.inspector) in self.paned.panes():
                self.paned.forget(self.inspector)
        self.config.save()

    def toggle_archived(self) -> None:
        self.config.show_archived = self.archived_var.get()
        self.config.save()
        self.sidebar.refresh()

    def open_assistant(self) -> None:
        if self.assistant_window and self.assistant_window.winfo_exists():
            self.assistant_window.lift()
            self.assistant_window.panel.on_selection()
            return
        self.assistant_window = AssistantWindow(self)

    def open_ai(self) -> None:
        if self.ai_window and self.ai_window.winfo_exists():
            self.ai_window.lift()
            return
        self.ai_window = AiWindow(self)

    def open_settings(self) -> None:
        if self.ws is None:
            return
        from .settings_dialog import SettingsDialog

        if SettingsDialog(self.root, self).run():
            self.refresh_all()

    def show_shortcuts(self) -> None:
        show_info(self.root, "Ctrl+N  task nou\nCtrl+F  căutare globală\nCtrl+S  salvează inspectorul\n"
                  "Ctrl+M  trimite e-mail din task\nInsert  câmpul de adăugare rapidă (în listă)\n"
                  "Alt+→ / Alt+←  subtask / scoate un nivel\n"
                  "F2  redenumește\nF5  reîmprospătează\nEnter în listă  deschide detaliile\n"
                  "Clic dreapta  meniu contextual\nCtrl+Enter în jurnal  adaugă notița", "Scurtături")

    def show_about(self) -> None:
        show_info(self.root, f"FocusDesk {__version__}\nOrganizator personal local: fișiere JSON/Markdown, "
                  "fără baze de date și fără servicii cloud.", "Despre")

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
            show_info(self.root, "Nu există încă o sesiune anterioară de reluat.")
            return
        self.select_node(node.id, reveal=True)
        self.start_session(node.id)

    def start_selected_session(self) -> None:
        node = self._selected_node()
        if node is None or node.kind != Kind.TASK:
            show_info(self.root, "Selectează un task pentru a începe o sesiune.")
            return
        self.start_session(node.id)

    def start_session(self, node_id: str, planned_session_id: str | None = None) -> None:
        if self.ws is None or self.timer is None:
            return
        if self.timer.active:
            show_info(self.root, "Există deja o sesiune activă. Oprește-o înainte să începi alta.")
            return
        node = self.ws.nodes.get(node_id)
        if node is None:
            return
        blockers = self.ws.unfinished_dependencies(node_id)
        if blockers and not confirm(self.root, "Task-ul depinde de task-uri nefinalizate:\n• " +
                                    "\n• ".join(b.title for b in blockers) + "\n\nContinui oricum?"):
            return
        open_opts = self._ask_session_open_options(node)
        if open_opts is False:
            return
        ok = self.run_write(lambda: self.timer.start(node_id, planned_session_id), success_text="Sesiune pornită")
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
            show_error(self.root, "\n".join(errors), "Deschidere parțială")
        self.config.session_open = {k: bool(v) for k, v in opts.items()}
        self.config.save()

    def toggle_pause(self) -> None:
        t = self.timer
        if t is None or not t.active:
            show_info(self.root, "Nu există o sesiune activă.")
            return
        if t.running:
            t.pause()
        else:
            gap = t.pending_gap
            if gap > 0:
                self._ask_gap(gap)
            else:
                t.resume()
        self._tick()

    def stop_session(self) -> bool:
        t = self.timer
        if t is None or not t.active:
            return True
        t.pause()
        node = self.ws.nodes.get(t.node_id) if t.node_id else None
        res = StopSessionDialog(self.root, self, node, t.seconds).run()
        if res is None:
            if t.state and t.state.state == "paused":
                t.resume()
            return False
        ok = self.run_write(lambda: t.stop(**res), success_text="Sesiune încheiată")
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
        self.create_checkpoint(node.id, "La finalul sesiunii", trigger="session_end", quiet_if_unchanged=True)

    # ---- jobs / checkpoints / openers ---------------------------------
    def run_job(self, work: Callable[..., Any], on_done: Callable[[Any], None] | None = None, *, name: str = "job",
                busy_text: str = "Se lucrează…", on_error: Callable[[BaseException], None] | None = None) -> Job:
        """Ruleaza `work(token)` intr-un thread; callback-urile se executa pe thread-ul UI."""
        self._busy += 1
        self.status.set_busy(busy_text)

        def finish() -> None:
            self._busy = max(0, self._busy - 1)
            if self._busy == 0:
                self.status.clear_busy()

        def ok(res: Any) -> None:
            finish()
            if on_done:
                try:
                    on_done(res)
                except Exception as exc:
                    log.exception("Callback job %s a eșuat", name)
                    show_error(self.root, f"Eroare: {exc}")

        def err(exc: BaseException) -> None:
            finish()
            if on_error:
                on_error(exc)
            elif isinstance(exc, FocusDeskError):
                show_error(self.root, str(exc))
            else:
                show_error(self.root, f"Eroare neașteptată: {exc}")

        return self.bridge.submit(work, ok, err, name=name)

    def create_checkpoint(self, node_id: str, description: str = "", *, trigger: str = "manual",
                          session_id: str | None = None, on_finished: Callable[[], None] | None = None,
                          quiet_if_unchanged: bool = False, force: bool = False) -> None:
        cs = self.checkpoints

        def done(m) -> None:
            if m is None:
                if not quiet_if_unchanged:
                    show_info(self.root, "Nicio modificare față de ultimul checkpoint; nu s-a creat unul nou.")
                self.status.set_message("Checkpoint: fără modificări")
            else:
                self.status.set_message(f"Checkpoint salvat ({len(m.files)} fișiere)")
            if on_finished:
                on_finished()

        def error(exc: BaseException) -> None:
            self.status.set_message("Checkpoint eșuat")
            show_error(self.root, f"Checkpoint-ul nu a fost salvat: {exc}", "Checkpoint")

        self.run_job(lambda tok: cs.create(node_id, description, trigger=trigger, session_id=session_id,
                                           force=force, cancel=tok),
                     done, on_error=error, name="checkpoint", busy_text="Se salvează checkpoint-ul…")

    # ---- calendar / planning -------------------------------------------
    def get_availability(self, start_day, end_day, on_done: Callable[[AvailabilityResult], None],
                         on_error: Callable[[BaseException], None] | None = None) -> None:
        """Disponibilitate din Outlook (daca e configurat) sau locala, cu mentiunea corecta a sursei."""
        self.outlook.get_availability(start_day, end_day, on_done, on_error)

    def availability_hint(self) -> str:
        o = self.outlook
        if o.enabled() and o.verified:
            return "Disponibilitate citită din Outlook (calendarul ales)."
        if o.enabled():
            return ("Outlook este configurat, dar neverificat în această sesiune; planificarea încearcă să-l citească "
                    "și, dacă nu reușește, folosește doar disponibilitatea locală.")
        return "Disponibilitate verificată doar local (calendarul extern nu este citit)."

    def on_sessions_changed(self) -> None:
        self.sidebar.refresh()
        if self.today.winfo_ismapped():
            self.today.refresh()

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
            show_info(self.root, "Nu există sesiuni viitoare de exportat.")
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Salvează fișierul .ics",
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

        self.run_write(mark, success_text="ICS exportat")
        show_info(self.root, f"Exportat — necesită import în calendar.\n{len(items)} sesiuni scrise în:\n{path}\n\n"
                  "Fișierul nu sincronizează automat. Reimportul actualizărilor/anulărilor depinde de clientul de calendar.",
                  "Export ICS")

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
                    m = cs.create(oid, "Checkpoint programat", trigger=trigger, missed_note=decision.note)
                    results.append((oid, "creat" if m else "fără modificări", None))
                except Exception as exc:  # raportat, nu ascuns
                    results.append((oid, "eșuat", str(exc)))
            return results

        def done(results) -> None:
            self._sched_running = False
            ok = sum(1 for r in results if r[1] == "creat")
            bad = [r for r in results if r[1] == "eșuat"]
            if not bad:
                sch.mark_ran(today)  # la erori nu marcam, ca sa reincerce
            msg = f"Checkpoint programat: {ok} create, {len(results) - ok - len(bad)} fără modificări, {len(bad)} eșuate"
            self.status.set_message(msg)
            if decision.note:
                show_info(self.root, decision.note, "Checkpoint programat ratat")
            if bad:
                show_error(self.root, "Checkpoint programat eșuat:\n" + "\n".join(
                    f"• {ws.nodes[o].title if o in ws.nodes else o}: {e}" for o, _s, e in bad[:5]), "Checkpoint")

        def failed(exc: BaseException) -> None:
            self._sched_running = False
            self.status.set_message(f"Checkpoint programat eșuat: {exc}")

        self.bridge.submit(work, done, failed, name="scheduled-checkpoint")

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
            show_error(self.root, "Nu există un folder de cod valid pentru acest nod.")
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
        try:
            self.mail_watch.tick()
            if self.current_view == "mail_review":
                self.mail_page.status.set(self.mail_watch.status)
        except Exception:
            self.mail_watch.status = "Evidența monitorizării nu poate fi citită; verifică datele locale."
        enabled = self.config.ai.enabled
        engine = self.ai.engine
        ai_text = "AI local · dezactivat" if not enabled else "AI local · în lucru" if engine and engine.busy else "AI local · activat, încărcare la cerere"
        self.ai_state.configure(text=ai_text)
        t = self.timer
        if t.recovered is None and t.state is not None:
            t.tick()
            node = self.ws.nodes.get(t.node_id or "")
            label = f"{'Sesiune' if t.running else 'Pauză'}: {node.title if node else '?'} — {format_seconds(t.seconds)}"
            if t.state.state == "paused" and t.pending_gap:
                label += " (nu a fost numărat intervalul de repaus)"
            self.status.set_timer(label, active=t.running)
        else:
            self.status.set_timer("Sesiune: niciuna")
        if self.current_view == "today":
            self.today.update_timer()
        self.update_session_buttons()
        self._tick_count += 1
        if self._tick_count % 30 == 0:
            self.check_scheduled_checkpoints()
        self._tick_job = self.root.after(1000, self._tick)

    def update_session_buttons(self) -> None:
        for b in self.session_buttons:
            b.update_state()

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
            ans = ask_choice(self.root, "Interval de inactivitate",
                             f"Între două verificări au trecut aproximativ {minutes} min (repaus/suspendare Windows "
                             "sau aplicație blocată). Intervalul NU a fost numărat ca lucru.\n\n"
                             "Cât din el vrei să adaugi la timpul lucrat?",
                             [("none", "Nimic (0 min)"), ("all", f"Tot ({minutes} min)"), ("custom", "Altă valoare…")])
            add = 0.0
            if ans == "all":
                add = gap
            elif ans == "custom":
                from .formats import parse_duration

                val = ask_string(self.root, "Timp de adăugat", "Minute (ex: 20, 1h):", "0", "Adaugă")
                try:
                    mins = parse_duration(val or "0") or 0
                    add = min(mins * 60, gap)
                except ValueError as exc:
                    show_error(self.root, str(exc))
            t.resume(count_gap_seconds=add)
        finally:
            self._gap_dialog_open = False

    def _handle_recovered_timer(self) -> None:
        t = self.timer
        if t is None or t.recovered is None:
            return
        rec = t.recovered
        saved = rec.state.accumulated_seconds
        ans = ask_choice(
            self.root, "Sesiune întreruptă",
            f"Ultima sesiune pentru „{rec.node_title}” nu a fost oprită corect (închidere, crash sau repaus).\n"
            f"Timp înregistrat până la ultima salvare: {format_seconds(saved)}.\n"
            "Timpul de după ultima salvare nu a fost numărat.",
            [("keep", "Păstrează timpul înregistrat"), ("custom", "Introdu durata manual"),
             ("discard", "Renunță la sesiune")])
        if ans == "keep":
            self.run_write(lambda: t.finalize_recovered(saved))
        elif ans == "custom":
            from .formats import parse_duration

            val = ask_string(self.root, "Durată lucrată", "Cât ai lucrat efectiv (ex: 45, 1h30)?",
                             str(int(saved // 60)), "Salvează")
            try:
                mins = parse_duration(val or "") if val else None
            except ValueError as exc:
                show_error(self.root, str(exc))
                mins = None
            if mins is not None:
                self.run_write(lambda: t.finalize_recovered(mins * 60))
        elif ans == "discard":
            t.discard()
        self.refresh_all()


class StartSessionDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: FocusDeskApp, node: Node, src_dir: Path | None, n_files: int) -> None:
        super().__init__(parent, "Începe sesiune", ok_text="▶ Începe")
        defaults = app.config.session_open
        ttk.Label(self.body, text=node.title, style="Section.TLabel", wraplength=420).pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", text="Alege ce să se deschidă acum (doar la cerere):").pack(
            anchor="w", pady=(2, 8))
        self.vars = {
            "vscode": tk.BooleanVar(value=defaults.get("vscode", False)),
            "explorer": tk.BooleanVar(value=defaults.get("explorer", False)),
            "files": tk.BooleanVar(value=defaults.get("files", False)),
        }
        if src_dir is not None:
            ttk.Checkbutton(self.body, variable=self.vars["vscode"],
                            text=f"Folderul de cod în VS Code ({src_dir})").pack(anchor="w", pady=2)
        ttk.Checkbutton(self.body, variable=self.vars["explorer"],
                        text="Folderul în Explorer" + (" (cod)" if src_dir else " (al nodului)")).pack(anchor="w", pady=2)
        if n_files:
            ttk.Checkbutton(self.body, variable=self.vars["files"],
                            text=f"Fișierele atașate ({n_files}; scripturile nu se deschid)").pack(anchor="w", pady=2)

    def collect(self) -> dict[str, bool]:
        return {k: v.get() for k, v in self.vars.items()}


class StopSessionDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: FocusDeskApp, node: Node | None, seconds: float) -> None:
        super().__init__(parent, "Oprește sesiunea", resizable=True, ok_text="Salvează și oprește")
        from ..domain.labels import STATUS_LABELS
        from .formats import duration_to_text

        self.app = app
        self.node = node
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text=node.title if node else "(task)", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(b, text=f"Timp lucrat efectiv: {format_seconds(seconds)} (timpul planificat nu se numără)",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(b, text="Ce am făcut").grid(row=2, column=0, sticky="nw", pady=3)
        self.text = tk.Text(b, height=5, width=52, wrap="word", font="TkTextFont")
        self.text.grid(row=2, column=1, sticky="ew", pady=3)
        self.text.focus_set()
        ttk.Label(b, text="Următorul pas").grid(row=3, column=0, sticky="w", pady=3)
        self.next_var = tk.StringVar(value=(node.next_action or "") if node else "")
        ttk.Entry(b, textvariable=self.next_var).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Label(b, text="Timp rămas").grid(row=4, column=0, sticky="w", pady=3)
        rem = node.remaining_minutes if node and node.remaining_minutes is not None else (
            node.estimated_minutes if node else None)
        self.rem_var = tk.StringVar(value=duration_to_text(rem))
        ttk.Entry(b, textvariable=self.rem_var, width=12).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(b, text="Status").grid(row=5, column=0, sticky="w", pady=3)
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
