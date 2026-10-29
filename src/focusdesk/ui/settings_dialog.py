"""Dialogul de setari (setarile workspace-ului din `_system/settings.json`)."""

from __future__ import annotations

from ..i18n import tr, LANGUAGES, language

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING, Callable

from ..domain.settings import BreakSlot, DaySchedule, Settings
from ..errors import FocusDeskError
from ..services.colleagues import import_colleagues, load_colleagues
from .common import ModalDialog, ScrollFrame, show_error
from .formats import format_date, parse_date, parse_tags
from .navigation_controls import AdaptiveNotebook

if TYPE_CHECKING:
    from .app import FocusDeskApp

from ..i18n import weekday_name
DAY_NAMES = [weekday_name(day) for day in range(7)]

# Etapele ulterioare adauga pagini: (titlu, builder(page_frame, dialog) -> collect_fn(settings) -> None)
EXTRA_PAGES: list[tuple[str, Callable]] = []


class SettingsDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, tr('ui.settings_dialog.setari'), resizable=True, ok_text=tr('ui.settings_dialog.salveaza'))
        self.body.pack_forget();self.buttons.pack_forget()
        self.buttons.pack(side='bottom',fill='x');self.body.pack(fill='both',expand=True)
        self.app = app
        self._language_only = app.ws is None
        self.nb = AdaptiveNotebook(self.body)
        self.nb.pack(fill="both", expand=True)
        self.collectors: list[Callable[[Settings], None]] = []
        if self._language_only:
            page=ttk.Frame(self.nb,padding=12);page.columnconfigure(0,weight=1);page.columnconfigure(1,weight=1)
            self.nb.add(page,text=tr('ui.settings_dialog.general'))
            self._language_fields(page,row=0)
            self._page_email()
            self.geometry('760x420');self.minsize(640,300)
            return
        self.s: Settings = app.ws.settings.model_copy(deep=True)
        self._page_general()
        self._page_colleagues()
        self._page_schedule()
        self._page_backup()
        self._page_checkpoints()
        self._page_email()
        from .outlook_ui import build_outlook_settings_page

        extra: list[tuple[str, Callable]] = [(tr('ui.outlook_ui.outlook'), build_outlook_settings_page), *EXTRA_PAGES]
        for title, builder in extra:
            page = ttk.Frame(self.nb, padding=12)
            self.nb.add(page, text=title)
            self.collectors.append(builder(page, self))
        self.geometry("900x720")
        self.minsize(760,600)
        if app.ws.read_only:
            self.ok_btn.state(["disabled"])

    # ---- pages ------------------------------------------------------
    def _page_email(self):
        from .gmail_ui import EmailSettingsPanel
        page=ttk.Frame(self.nb,padding=10)
        self.nb.add(page,text=tr('gmail.integrations'))
        box=ttk.LabelFrame(page,text=tr('gmail.settings_title'),padding=8)
        box.pack(fill='both',expand=True)
        self.email_panel=EmailSettingsPanel(box,self.app)
        self.email_panel.pack(fill='both',expand=True)

    def _page_general(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text=tr('ui.settings_dialog.general'))
        p.columnconfigure(1, weight=1)
        ws = self.app.ws
        self.name_var = tk.StringVar(value=ws.name)
        ttk.Label(p, text=tr('ui.settings_dialog.nume_workspace')).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(p, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(p, text=tr('ui.settings_dialog.folder_date')).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(p, text=str(ws.root)).grid(row=1, column=1, sticky="w", pady=4)
        self.tz_var = tk.StringVar(value=self.s.timezone)
        ttk.Label(p, text=tr('ui.settings_dialog.fus_orar')).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(p, textvariable=self.tz_var).grid(row=2, column=1, sticky="ew", pady=4)
        self.max_today_var = tk.StringVar(value=str(self.s.max_today_priorities))
        ttk.Label(p, text=tr('ui.settings_dialog.prioritati_maxime_pe_zi')).grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(p, textvariable=self.max_today_var, width=6).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(p, style="Muted.TLabel", wraplength=560, text=(
            tr('ui.settings_dialog.datele_sunt_stocate_in_afara_executabilului_in_folderul_de_mai_sus_act'))).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))

        self._language_fields(p,row=5)

        def collect(s: Settings) -> None:
            s.timezone = self.tz_var.get().strip()
            s.max_today_priorities = int(self.max_today_var.get())

        self.collectors.append(collect)

    def _language_fields(self,p,*,row):
        language_box = ttk.LabelFrame(p, text=tr('settings.language'), padding=10)
        language_box.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(18,0))
        language_box.columnconfigure(0, weight=1)
        self.language_var = tk.StringVar(value=LANGUAGES[self.app.config.language])
        ttk.Combobox(language_box, textvariable=self.language_var, values=list(LANGUAGES.values()),
                     state='readonly').grid(row=0,column=0,sticky='ew')
        ttk.Button(language_box, text=tr('settings.language_apply'), command=self.save_language).grid(row=1,column=0,sticky='w',pady=(8,0))
        self.language_notice=ttk.Label(language_box,text=tr('settings.language_restart'),wraplength=600)
        self.language_notice.grid(row=2,column=0,sticky='ew',pady=(8,0))
        language_box.bind('<Configure>',lambda event:self.language_notice.configure(wraplength=max(200,event.width-24)))


    def save_language(self):
        code=next(code for code,name in LANGUAGES.items() if name==self.language_var.get())
        previous=self.app.config.language
        self.app.config.language=code
        try:
            from ..storage.atomic import atomic_write_json
            atomic_write_json(self.app.config.path(),self.app.config.model_dump(mode='json'),keep_backup=False)
        except Exception as exc:
            self.app.config.language=previous
            show_error(self,tr('settings.language_error',detail=str(exc)))
            return False
        self.language_notice.configure(text=tr('settings.language_saved',name=LANGUAGES[code]))
        return True

    def _page_colleagues(self) -> None:
        page = ttk.Frame(self.nb, padding=12)
        self.nb.add(page, text=tr('ui.settings_dialog.colegi'))
        self.colleagues_status = tk.StringVar()
        try:
            self.colleagues_status.set(tr('ui.settings_dialog.colegi_salvati', len_load_colleagues_self_app_ws=len(load_colleagues(self.app.ws))))
        except FocusDeskError as exc:
            self.colleagues_status.set(str(exc))
        ttk.Label(page, textvariable=self.colleagues_status, wraplength=600).pack(anchor="w", pady=(0, 12))
        self.import_colleagues_btn = ttk.Button(page, text=tr('ui.settings_dialog.incarca_excel_colegi'), command=self._import_colleagues)
        self.import_colleagues_btn.pack(anchor="w")
        if self.app.ws.read_only:
            self.import_colleagues_btn.state(["disabled"])

    def _import_colleagues(self) -> None:
        path = filedialog.askopenfilename(parent=self, title=tr('ui.settings_dialog.lista_de_colegi'), filetypes=[(tr('ui.settings_dialog.excel'), "*.xlsx")])
        if not path:
            return
        people = []

        def perform() -> None:
            people.extend(import_colleagues(self.app.ws, Path(path)))

        if self.app.run_write(perform, success_text=tr('ui.settings_dialog.lista_de_colegi_a_fost_importata')):
            self.colleagues_status.set(tr('ui.settings_dialog.colegi_salvati_2', len_people=len(people)))

    def _page_schedule(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text=tr('ui.settings_dialog.program_de_lucru'))
        p.columnconfigure(5, weight=1)
        ttk.Label(p, text=tr('ui.settings_dialog.zi'), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(p, text=tr('ui.settings_dialog.activa')).grid(row=0, column=1)
        ttk.Label(p, text=tr('ui.meetings.de_la')).grid(row=0, column=2)
        ttk.Label(p, text=tr('ui.meetings.pana_la')).grid(row=0, column=3)
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
        ttk.Label(p, text=tr('ui.settings_dialog.pauze_hh_mm_hh_mm_separate_prin_virgula')).grid(row=r, column=0, columnspan=3, sticky="w",
                                                                              pady=(10, 2))
        self.breaks_var = tk.StringVar(value=", ".join(f"{b.start}-{b.end}" for b in self.s.breaks))
        ttk.Entry(p, textvariable=self.breaks_var, width=40).grid(row=r + 1, column=0, columnspan=4, sticky="w")
        ttk.Label(p, text=tr('ui.settings_dialog.zile_nelucratoare_zz_ll_aaaa_separate_prin_virgula')).grid(
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
            "min_session_minutes": tr('ui.settings_dialog.durata_minima_sesiune_min'), "max_session_minutes": tr('ui.settings_dialog.durata_maxima_sesiune_min'),
            "gap_minutes": tr('ui.settings_dialog.pauza_intre_sesiuni_min'), "daily_reserve_minutes": tr('ui.settings_dialog.rezerva_zilnica_pentru_urgente_min'),
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
        self.nb.add(p, text=tr('ui.settings_dialog.backup'))
        p.columnconfigure(1, weight=1)
        b = self.s.backup
        self.b_daily = tk.BooleanVar(value=b.daily)
        self.b_full = tk.BooleanVar(value=b.include_files)
        self.b_ret = tk.StringVar(value=str(b.retention))
        self.b_ext = tk.StringVar(value=b.external_dir or "")
        ttk.Checkbutton(p, text=tr('ui.settings_dialog.backup_zilnic_la_prima_pornire_a_zilei'), variable=self.b_daily).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(p, text=tr('ui.settings_dialog.backup_zilnic_complet_cu_fisiere_administrate_altfel_doar_metadate'),
                        variable=self.b_full).grid(row=1, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(p, text=tr('ui.settings_dialog.pastreaza_ultimele')).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(p, textvariable=self.b_ret, width=6).grid(row=2, column=1, sticky="w")
        ttk.Label(p, text=tr('ui.settings_dialog.folder_extern_optional')).grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(p, textvariable=self.b_ext).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Button(p, text=tr('common.choose'), command=self._pick_ext).grid(row=3, column=2, padx=4)
        ttk.Label(p, style="Muted.TLabel", wraplength=560, justify="left", text=(
            tr('ui.settings_dialog.un_backup_pe_acelasi_disc_cu_datele_nu_protejeaza_de_defectarea_discul'))).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))

        def collect(s: Settings) -> None:
            s.backup.daily = self.b_daily.get()
            s.backup.include_files = self.b_full.get()
            s.backup.retention = max(1, int(self.b_ret.get()))
            s.backup.external_dir = self.b_ext.get().strip() or None

        self.collectors.append(collect)

    def _page_checkpoints(self) -> None:
        p = ttk.Frame(self.nb, padding=12)
        self.nb.add(p, text=tr('ui.settings_dialog.versiuni_vs_code'))
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
        ttk.Checkbutton(p, text=tr('ui.settings_dialog.checkpoint_automat_la_finalul_sesiunii_daca_exista_folder_de_cod'),
                        variable=self.c_end).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(p, text=tr('ui.settings_dialog.checkpoint_zilnic_programat'), variable=self.c_daily).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(p, text=tr('ui.settings_dialog.ora_hh_mm')).grid(row=2, column=0, sticky="w")
        ttk.Entry(p, textvariable=self.c_time, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(p, style="Muted.TLabel", wraplength=600, text=(
            tr('ui.settings_dialog.programarea_functioneaza_doar_cat_timp_focusdesk_ruleaza_la_repornire'))).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(2, 8))
        for r, (lbl, var) in enumerate(((tr('ui.settings_dialog.pastreaza_ultimele_checkpoint_uri'), self.c_ret),
                                        (tr('ui.settings_dialog.limita_totala_mb'), self.c_total), (tr('ui.settings_dialog.limita_pe_fisier_mb'), self.c_file)), 4):
            ttk.Label(p, text=lbl).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(p, textvariable=var, width=8).grid(row=r, column=1, sticky="w")
        ttk.Label(p, text=tr('ui.settings_dialog.excluderi_nume_sabloane_separate_prin_virgula')).grid(row=7, column=0, columnspan=3,
                                                                                    sticky="w", pady=(8, 2))
        ttk.Entry(p, textvariable=self.c_excl).grid(row=8, column=0, columnspan=3, sticky="ew")
        ttk.Label(p, text=tr('ui.settings_dialog.executabil_vs_code_optional')).grid(row=9, column=0, sticky="w", pady=(12, 2))
        ttk.Entry(p, textvariable=self.vs_var).grid(row=9, column=1, sticky="ew", pady=(12, 2))
        ttk.Button(p, text=tr('common.choose'), command=self._pick_vscode).grid(row=9, column=2, padx=4, pady=(12, 2))
        ttk.Label(p, style="Muted.TLabel", wraplength=600, text=(
            tr('ui.settings_dialog.focusdesk_vede_doar_fisierele_salvate_pe_disc_nu_textul_nesalvat_din_v'))).grid(
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
        f = filedialog.askopenfilename(parent=self, title="Code.exe", filetypes=[(tr('ui.settings_dialog.executabil'), "*.exe")])
        if f:
            self.vs_var.set(f)

    def _pick_ext(self) -> None:
        d = filedialog.askdirectory(parent=self, title=tr('ui.settings_dialog.folder_extern_pentru_backup'))
        if d:
            self.b_ext.set(d)

    # ---- result -----------------------------------------------------
    def validate(self) -> bool:
        if self._language_only:return True
        try:
            new = self.s.model_copy(deep=True)
            for c in self.collectors:
                c(new)
            Settings.model_validate(new.model_dump())
            self._new = new
            return True
        except (ValueError, FocusDeskError) as exc:
            show_error(self, tr('ui.settings_dialog.setari_invalide', exc=exc))
            return False

    def collect(self) -> bool:
        if self._language_only:return self.save_language()
        ws = self.app.ws
        ok = self.app.run_write(lambda: (ws.update_settings(self._new),
                                         ws.repo.rename_workspace(self.name_var.get())))
        if ok:
            self.save_language()
            self.app.ws_label.configure(text=ws.name)
            self.app.root.title(tr('ui.settings_dialog.focusdesk', ws_name=ws.name))
        return ok
