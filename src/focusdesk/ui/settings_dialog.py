"""Dialogul de setari (setarile workspace-ului din `_system/settings.json`)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING, Callable

from ..domain.settings import BreakSlot, DaySchedule, Settings
from ..errors import FocusDeskError
from ..services.colleagues import import_colleagues, load_colleagues
from .common import ModalDialog, ScrollFrame, show_error
from .formats import format_date, parse_date, parse_tags

if TYPE_CHECKING:
    from .app import FocusDeskApp

DAY_NAMES = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]

# Etapele ulterioare adauga pagini: (titlu, builder(page_frame, dialog) -> collect_fn(settings) -> None)
EXTRA_PAGES: list[tuple[str, Callable]] = []


class SettingsDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, "Setări", resizable=True, ok_text="Salvează")
        self.app = app
        self.s: Settings = app.ws.settings.model_copy(deep=True)
        self.nb = ttk.Notebook(self.body)
        self.nb.pack(fill="both", expand=True)
        self.collectors: list[Callable[[Settings], None]] = []
        self._page_general()
        self._page_colleagues()
        self._page_schedule()
        self._page_backup()
        self._page_checkpoints()
        from .outlook_ui import build_outlook_settings_page

        extra: list[tuple[str, Callable]] = [("Outlook", build_outlook_settings_page), *EXTRA_PAGES]
        for title, builder in extra:
            page = ttk.Frame(self.nb, padding=12)
            self.nb.add(page, text=title)
            self.collectors.append(builder(page, self))
        self.geometry("900x720")
        self.minsize(760,600)
        if app.ws.read_only:
            self.ok_btn.state(["disabled"])

    # ---- pages ------------------------------------------------------
    def _page_general(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text="General")
        p.columnconfigure(1, weight=1)
        ws = self.app.ws
        self.name_var = tk.StringVar(value=ws.name)
        ttk.Label(p, text="Nume workspace").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(p, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(p, text="Folder date").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(p, text=str(ws.root)).grid(row=1, column=1, sticky="w", pady=4)
        self.tz_var = tk.StringVar(value=self.s.timezone)
        ttk.Label(p, text="Fus orar").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(p, textvariable=self.tz_var).grid(row=2, column=1, sticky="ew", pady=4)
        self.max_today_var = tk.StringVar(value=str(self.s.max_today_priorities))
        ttk.Label(p, text="Priorități maxime pe zi").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(p, textvariable=self.max_today_var, width=6).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(p, style="Muted.TLabel", wraplength=560, text=(
            "Datele sunt stocate în afara executabilului, în folderul de mai sus. Actualizarea aplicației nu le șterge. "
            "Indexul din _system/index.json este doar cache și poate fi șters oricând.")).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))

        def collect(s: Settings) -> None:
            s.timezone = self.tz_var.get().strip()
            s.max_today_priorities = int(self.max_today_var.get())

        self.collectors.append(collect)

    def _page_colleagues(self) -> None:
        page = ttk.Frame(self.nb, padding=12)
        self.nb.add(page, text="Colegi")
        self.colleagues_status = tk.StringVar()
        try:
            self.colleagues_status.set(f"Colegi salvați: {len(load_colleagues(self.app.ws))}")
        except FocusDeskError as exc:
            self.colleagues_status.set(str(exc))
        ttk.Label(page, textvariable=self.colleagues_status, wraplength=600).pack(anchor="w", pady=(0, 12))
        self.import_colleagues_btn = ttk.Button(page, text="Încarcă Excel colegi…", command=self._import_colleagues)
        self.import_colleagues_btn.pack(anchor="w")
        if self.app.ws.read_only:
            self.import_colleagues_btn.state(["disabled"])

    def _import_colleagues(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Lista de colegi", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        people = []

        def perform() -> None:
            people.extend(import_colleagues(self.app.ws, Path(path)))

        if self.app.run_write(perform, success_text="Lista de colegi a fost importată"):
            self.colleagues_status.set(f"Colegi salvați: {len(people)}")

    def _page_schedule(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text="Program de lucru")
        p.columnconfigure(5, weight=1)
        ttk.Label(p, text="Zi", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(p, text="Activă").grid(row=0, column=1)
        ttk.Label(p, text="De la").grid(row=0, column=2)
        ttk.Label(p, text="Până la").grid(row=0, column=3)
        self.day_vars: list[tuple[tk.BooleanVar, tk.StringVar, tk.StringVar]] = []
        for i, name in enumerate(DAY_NAMES):
            d = self.s.work_hours.get(str(i), DaySchedule(enabled=False))
            en, st, en_t = tk.BooleanVar(value=d.enabled), tk.StringVar(value=d.start), tk.StringVar(value=d.end)
            ttk.Label(p, text=name).grid(row=i + 1, column=0, sticky="w", pady=2)
            ttk.Checkbutton(p, variable=en).grid(row=i + 1, column=1)
            ttk.Entry(p, textvariable=st, width=7).grid(row=i + 1, column=2, padx=4)
            ttk.Entry(p, textvariable=en_t, width=7).grid(row=i + 1, column=3, padx=4)
            self.day_vars.append((en, st, en_t))
        r = 9
        ttk.Label(p, text="Pauze (HH:MM-HH:MM, separate prin virgulă)").grid(row=r, column=0, columnspan=3, sticky="w",
                                                                              pady=(10, 2))
        self.breaks_var = tk.StringVar(value=", ".join(f"{b.start}-{b.end}" for b in self.s.breaks))
        ttk.Entry(p, textvariable=self.breaks_var, width=40).grid(row=r + 1, column=0, columnspan=4, sticky="w")
        ttk.Label(p, text="Zile nelucrătoare (ZZ.LL.AAAA, separate prin virgulă)").grid(
            row=r + 2, column=0, columnspan=4, sticky="w", pady=(10, 2))
        self.hol_var = tk.StringVar(value=", ".join(format_date(h) for h in self.s.holidays))
        ttk.Entry(p, textvariable=self.hol_var, width=70).grid(row=r + 3, column=0, columnspan=6, sticky="ew")
        self.num_vars = {
            "min_session_minutes": tk.StringVar(value=str(self.s.min_session_minutes)),
            "max_session_minutes": tk.StringVar(value=str(self.s.max_session_minutes)),
            "gap_minutes": tk.StringVar(value=str(self.s.gap_minutes)),
            "daily_reserve_minutes": tk.StringVar(value=str(self.s.daily_reserve_minutes)),
        }
        labels = {
            "min_session_minutes": "Durată minimă sesiune (min)", "max_session_minutes": "Durată maximă sesiune (min)",
            "gap_minutes": "Pauză între sesiuni (min)", "daily_reserve_minutes": "Rezervă zilnică pentru urgențe (min)",
        }
        for j, (k, var) in enumerate(self.num_vars.items()):
            ttk.Label(p, text=labels[k]).grid(row=r + 4 + j, column=0, columnspan=3, sticky="w", pady=2)
            ttk.Entry(p, textvariable=var, width=7).grid(row=r + 4 + j, column=3, sticky="w")

        def collect(s: Settings) -> None:
            week = {}
            for i, (en, st, en_t) in enumerate(self.day_vars):
                week[str(i)] = DaySchedule(enabled=en.get(), start=st.get().strip(), end=en_t.get().strip())
            s.work_hours = week
            slots = []
            for chunk in [c.strip() for c in self.breaks_var.get().split(",") if c.strip()]:
                a, _, b = chunk.partition("-")
                slots.append(BreakSlot(start=a.strip(), end=b.strip()))
            s.breaks = slots
            s.holidays = [d for d in (parse_date(c) for c in self.hol_var.get().split(",")) if d]
            for k, var in self.num_vars.items():
                setattr(s, k, int(var.get()))

        self.collectors.append(collect)

    def _page_backup(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text="Backup")
        p.columnconfigure(1, weight=1)
        b = self.s.backup
        self.b_daily = tk.BooleanVar(value=b.daily)
        self.b_full = tk.BooleanVar(value=b.include_files)
        self.b_ret = tk.StringVar(value=str(b.retention))
        self.b_ext = tk.StringVar(value=b.external_dir or "")
        ttk.Checkbutton(p, text="Backup zilnic la prima pornire a zilei", variable=self.b_daily).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(p, text="Backup zilnic complet (cu fișiere administrate); altfel doar metadate",
                        variable=self.b_full).grid(row=1, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(p, text="Păstrează ultimele").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(p, textvariable=self.b_ret, width=6).grid(row=2, column=1, sticky="w")
        ttk.Label(p, text="Folder extern (opțional)").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(p, textvariable=self.b_ext).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Button(p, text="Alege…", command=self._pick_ext).grid(row=3, column=2, padx=4)
        ttk.Label(p, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Un backup pe același disc cu datele nu protejează de defectarea discului; alege un folder pe alt disc "
            "sau o partajare de rețea. Backup-urile nu se includ în propriul backup.")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))

        def collect(s: Settings) -> None:
            s.backup.daily = self.b_daily.get()
            s.backup.include_files = self.b_full.get()
            s.backup.retention = max(1, int(self.b_ret.get()))
            s.backup.external_dir = self.b_ext.get().strip() or None

        self.collectors.append(collect)

    def _page_checkpoints(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text="Versiuni & VS Code")
        p.columnconfigure(1, weight=1)
        c = self.s.checkpoints
        self.c_end = tk.BooleanVar(value=c.on_session_end)
        self.c_daily = tk.BooleanVar(value=c.enabled_daily)
        self.c_time = tk.StringVar(value=c.daily_time)
        self.c_ret = tk.StringVar(value=str(c.retention))
        self.c_total = tk.StringVar(value=str(c.max_total_mb))
        self.c_file = tk.StringVar(value=str(c.max_file_mb))
        self.c_excl = tk.StringVar(value=", ".join(c.exclude_names))
        self.vs_var = tk.StringVar(value=self.s.vscode_path or "")
        ttk.Checkbutton(p, text="Checkpoint automat la finalul sesiunii (dacă există folder de cod)",
                        variable=self.c_end).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(p, text="Checkpoint zilnic programat", variable=self.c_daily).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(p, text="Ora (HH:MM)").grid(row=2, column=0, sticky="w")
        ttk.Entry(p, textvariable=self.c_time, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(p, style="Muted.TLabel", wraplength=600, text=(
            "Programarea funcționează doar cât timp FocusDesk rulează. La repornire, dacă ora programată a fost "
            "ratată, se creează un checkpoint al stării curente și se notează că ora a fost ratată; starea istorică "
            "din momentul în care aplicația era închisă nu poate fi reconstruită.")).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(2, 8))
        for r, (lbl, var) in enumerate((("Păstrează ultimele (checkpoint-uri)", self.c_ret),
                                        ("Limită totală (MB)", self.c_total), ("Limită pe fișier (MB)", self.c_file)), 4):
            ttk.Label(p, text=lbl).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(p, textvariable=var, width=8).grid(row=r, column=1, sticky="w")
        ttk.Label(p, text="Excluderi (nume/șabloane, separate prin virgulă)").grid(row=7, column=0, columnspan=3,
                                                                                    sticky="w", pady=(8, 2))
        ttk.Entry(p, textvariable=self.c_excl).grid(row=8, column=0, columnspan=3, sticky="ew")
        ttk.Label(p, text="Executabil VS Code (opțional)").grid(row=9, column=0, sticky="w", pady=(12, 2))
        ttk.Entry(p, textvariable=self.vs_var).grid(row=9, column=1, sticky="ew", pady=(12, 2))
        ttk.Button(p, text="Alege…", command=self._pick_vscode).grid(row=9, column=2, padx=4, pady=(12, 2))
        ttk.Label(p, style="Muted.TLabel", wraplength=600, text=(
            "FocusDesk vede doar fișierele salvate pe disc, nu textul nesalvat din VS Code. Poți activa Auto Save în "
            "VS Code; aplicația nu modifică setările VS Code. Lipsă = detectare automată.")).grid(
            row=10, column=0, columnspan=3, sticky="w", pady=(8, 0))

        def collect(s: Settings) -> None:
            s.checkpoints.on_session_end = self.c_end.get()
            s.checkpoints.enabled_daily = self.c_daily.get()
            s.checkpoints.daily_time = self.c_time.get().strip()
            s.checkpoints.retention = max(1, int(self.c_ret.get()))
            s.checkpoints.max_total_mb = max(1, int(self.c_total.get()))
            s.checkpoints.max_file_mb = max(1, int(self.c_file.get()))
            s.checkpoints.exclude_names = parse_tags(self.c_excl.get())
            s.vscode_path = self.vs_var.get().strip() or None

        self.collectors.append(collect)

    def _pick_vscode(self) -> None:
        f = filedialog.askopenfilename(parent=self, title="Code.exe", filetypes=[("Executabil", "*.exe")])
        if f:
            self.vs_var.set(f)

    def _pick_ext(self) -> None:
        d = filedialog.askdirectory(parent=self, title="Folder extern pentru backup")
        if d:
            self.b_ext.set(d)

    # ---- result -----------------------------------------------------
    def validate(self) -> bool:
        try:
            new = self.s.model_copy(deep=True)
            for c in self.collectors:
                c(new)
            Settings.model_validate(new.model_dump())
            self._new = new
            return True
        except (ValueError, FocusDeskError) as exc:
            show_error(self, f"Setări invalide: {exc}")
            return False

    def collect(self) -> bool:
        ws = self.app.ws
        ok = self.app.run_write(lambda: (ws.update_settings(self._new),
                                         ws.repo.rename_workspace(self.name_var.get())))
        if ok:
            self.app.ws_label.configure(text=ws.name)
            self.app.root.title(f"FocusDesk — {ws.name}")
        return ok
