"""Exploratorul folderelor reale, cu asocierile și referințele existente."""

from __future__ import annotations

from ..i18n import tr

import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from ..domain.models import Kind
from ..errors import FocusDeskError
from ..integrations import system
from ..services.files import FileService, NameConflict
from .common import ModalDialog, Tooltip, ask_choice, confirm, make_tree, show_error, show_info
from .inspector import InspectorTab
from .file_explorer import FileExplorer
from ..services.files import normalized_file_key

if TYPE_CHECKING:
    from .app import FocusDeskApp

class ReferenceDialog(ModalDialog):
    """Metadata-only access to old references, including those in unavailable subfolders."""
    enter_confirms = False

    def __init__(self, parent, node):
        super().__init__(parent, tr('ui.tab_files.legaturi_si_referinte_existente'), resizable=True, ok_text=tr('ui.tab_files.alege_referinta'))
        self.geometry("740x400")
        self.minsize(520, 300)
        self.body.pack_forget()
        self.buttons.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        ttk.Label(self.body, text=tr('ui.tab_files.aceasta_este_lista_referintelor_salvate_exploratorul_afiseaza_separat'),
                  style="Muted.TLabel", wraplength=440).pack(fill="x", pady=4)
        self.tv, frame = make_tree(self.body, [("name", tr('ui.file_picker.nume'), 170), ("mode", tr('ui.tab_files.mod'), 90), ("path", tr('ui.tab_files.cale'), 390)])
        frame.pack(fill="both", expand=True)
        for att in node.attachments:
            self.tv.insert("", "end", iid=att.id, values=(att.name, tr('ui.tab_files.extern') if att.mode == "external" else tr('ui.tab_files.administrat'), att.path))
        self.tv.bind("<Return>", lambda _e: self._on_ok())
        self.tv.bind("<Double-1>", lambda _e: self._on_ok())

    def validate(self):
        return bool(self.tv.selection())

    def collect(self):
        return self.tv.selection()[0]


class AddAttachmentDialog(ModalDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, tr('ui.tab_files.adauga_fisier_sau_folder'), ok_text=tr('ui.tab_subtasks.adauga'))
        self.mode = tk.StringVar(value="managed")
        self.paths: list[str] = []
        ttk.Radiobutton(self.body, variable=self.mode, value="managed",
                        text=tr('ui.tab_files.copie_administrata_in_workspace')).pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=440, text=(
            tr('ui.tab_files.fisierul_se_copiaza_in_folderul_nodului_files_ramane_alaturi_de_task_i'))).pack(anchor="w", padx=(22, 0), pady=(0, 8))
        ttk.Radiobutton(self.body, variable=self.mode, value="external",
                        text=tr('ui.tab_files.legatura_externa_ramane_unde_este')).pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=440, text=(
            tr('ui.tab_files.se_memoreaza_doar_calea_nu_se_copiaza_nimic_daca_fisierul_este_mutat_s'))).pack(
            anchor="w", padx=(22, 0), pady=(0, 8))
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Button(row, text=tr('ui.tab_files.alege_fisiere'), command=self._pick_files).pack(side="left")
        ttk.Button(row, text=tr('ui.tab_files.alege_folder'), command=self._pick_dir).pack(side="left", padx=6)
        self.summary = ttk.Label(self.body, text=tr('ui.tab_files.nimic_ales'), style="Muted.TLabel", wraplength=440)
        self.summary.pack(anchor="w", pady=(8, 0))

    def _pick_files(self) -> None:
        sel = filedialog.askopenfilenames(parent=self, title=tr('ui.tab_files.alege_fisierele'))
        if sel:
            self.paths = list(sel)
            self._summ()

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(parent=self, title=tr('ui.tab_files.alege_folderul'))
        if d:
            self.paths = [d]
            self._summ()

    def _summ(self) -> None:
        self.summary.configure(text="\n".join(self.paths[:6]) + (tr('ui.tab_files.si_inca', len_self_paths_6=len(self.paths) - 6) if len(self.paths) > 6 else ""))

    def validate(self) -> bool:
        if not self.paths:
            show_error(self, tr('ui.tab_files.alege_cel_putin_un_fisier_sau_folder'))
            return False
        return True

    def collect(self):
        return self.mode.get(), self.paths


class FilesTab(InspectorTab):
    title = "Fișiere"

    def __init__(self, parent, app, *, on_expand=None):
        super().__init__(parent, app)
        self._ws = None
        self._action_pending = False
        self._action_serial = 0
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=6)
        self.btn_add = ttk.Button(toolbar, text=tr('ui.tab_details.adauga'), command=self._add)
        self.btn_add.pack(side="left")
        self.refresh_btn = ttk.Button(toolbar, text=tr('ui.tab_files.actualizeaza'), command=self.refresh)
        self.refresh_btn.pack(side="left", padx=4)
        self.more = ttk.Menubutton(toolbar, text=tr('ui.meetings.actiuni'))
        self.more.pack(side="left")
        self.menu = tk.Menu(self.more, tearoff=False)
        self.more.configure(menu=self.menu)
        for label, command in ((tr('ui.user_guide.deschide'), self._open), (tr('ui.tab_files.deschide_in_explorer'), self._reveal),
                               (tr('ui.tab_files.deschide_in_vs_code'), self._vscode), (tr('ui.tab_files.copiaza_calea'), self._copy_path),
                               (tr('ui.tab_files.ataseaza_la_e_mail'), self._email)):
            self.menu.add_command(label=label, command=command)
        self.menu.add_separator()
        for label, command in ((tr('ui.tab_files.alege_folderul_proiectului'), self._set_code),
                               (tr('ui.tab_files.foloseste_folderul_administrat_existent_files'), self._set_managed_code),
                               (tr('ui.tab_files.elimina_asocierea_opreste_mostenirea'), self._clear_code),
                               (tr('ui.tab_files.relocalizeaza_legatura'), self._relocate),
                               (tr('ui.tab_files.elimina_doar_legatura_referinta'), self._remove),
                               (tr('ui.tab_files.sterge_copia_administrata_si_referinta'), self._remove_copy)):
            self.menu.add_command(label=label, command=command)
        self.menu.add_command(label=tr('ui.tab_files.legaturi_si_referinte_existente_2'), command=self._manage_references)
        if on_expand:
            self.menu.add_command(label=tr('ui.tab_files.mai_mult_spatiu_pentru_fisiere'), command=on_expand)
        self.menu.configure(postcommand=self._menu_state)
        self.code_lbl = ttk.Label(self, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.code_lbl.pack(fill="x", padx=8)
        self.path_tip = Tooltip(self.code_lbl, tr('ui.tab_files.calea_radacinii_si_a_elementului_selectat'))
        self.code_note = ttk.Label(self, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.code_note.pack(fill="x", padx=8, pady=(2, 4))
        self.choose = ttk.Frame(self)
        ttk.Button(self.choose, text=tr('ui.tab_files.alege_folderul_proiectului'), command=self._set_code).pack(side="left")
        ttk.Button(self.choose, text=tr('ui.tab_files.foloseste_files'), command=self._set_managed_code).pack(side="left", padx=4)
        self.explorer = FileExplorer(self, app, on_open=self._open, on_select=self._selection_changed)
        self.explorer.pack(fill="both", expand=True, padx=8, pady=4)
        self.tv = self.explorer.tv
        self.tv.bind("<Button-3>", self._context_menu)
        self.tv.bind("<Menu>", self._keyboard_menu)
        self.tv.bind("<Shift-F10>", self._keyboard_menu)
        for widget in (self.btn_add, self.refresh_btn, self.more):
            widget.bind("<F5>", lambda _e: self.refresh() or "break")
        self.bind("<Configure>", self._resize)

    @property
    def fs(self):
        return self.app.files

    def _resize(self, event):
        if event.widget is self:
            for label in (self.code_lbl, self.code_note):
                label.configure(wraplength=max(180, event.width - 24))

    def applies_to(self, node):
        return node.kind != Kind.FOLDER

    def load(self, node):
        if self._ws is not self.app.ws or self.node_id != node.id:
            self._action_serial += 1
            self._action_pending = False
        self._ws = self.app.ws
        super().load(node)
        sources = self.fs.explorer_sources(node.id)
        work = next((s for s in sources if s.key == 'work'), None)
        self.code_lbl.configure(text=str(work.path) if work and work.path else
                                tr('ui.tab_files.folderul_de_lucru_este_indisponibil') if work else tr('ui.tab_files.niciun_folder_de_lucru_asociat'))
        self.code_note.configure(text=(work.note or work.error) if work else tr('ui.tab_files.poti_explora_files_sau_asocia_un_folder_extern_fara_copiere'))
        if work is None and not self.app.ws.read_only:
            self.choose.pack(fill='x', padx=8, before=self.explorer)
        else:
            self.choose.pack_forget()
        self.btn_add.state(['disabled'] if self.app.ws.read_only else ['!disabled'])
        references = []
        for att in node.attachments:
            try: references.append((self.fs.resolve(node.id, att), att.is_dir))
            except FocusDeskError: pass
        self.explorer.load(self.app.ws, node.id, sources, references)

    def refresh(self):
        self.explorer.refresh()

    def stop_monitoring(self):
        self.explorer.stop()

    def detach_workspace(self):
        self._action_serial += 1
        self._action_pending = False
        self._ws = self.node_id = None
        self.explorer.detach_workspace()

    def _selection_changed(self):
        selection = self.tv.selection()
        row = self.explorer.rows.get(selection[0]) if selection else None
        if row and row['entry'] is None and row.get('source'):
            self.code_lbl.configure(text=row['source'].label)
            self.code_note.configure(text=row['source'].error)
            return
        selected = self.explorer.selected()
        if selected:
            _, row = selected[0]
            source = row.get('source') or next((s for s in self.explorer.sources if s.path == row['root']), None)
            path = row['entry'].path
            self.code_lbl.configure(text=str(row['root']))
            self.path_tip.text = tr('ui.tab_files.radacina_selectat', row_root=row['root'], path=path)
            note = source.note if source else ''
            detail = row.get('error') or row['entry'].detail
            self.code_note.configure(text=note + ('\n' + detail if detail else ''))

    def _selected_att(self):
        override = getattr(self, '_reference_id', None)
        if override and self._writable():
            return next((att for att in self._ws.get(self.node_id).attachments if att.id == override), None)
        selected = self.tv.selection()
        if not selected or not self.node_id or self.app.ws is not self._ws or self.node_id not in self._ws.nodes:
            return None
        row = self.explorer.rows.get(selected[0])
        if row is None:
            return None
        source = row.get('source')
        ids = source.reference_ids if source else ()
        for att in self.fs.ws.get(self.node_id).attachments:
            if att.id in ids:
                return att
            try:
                if row['entry'] and normalized_file_key(self.fs.resolve(self.node_id, att)) == normalized_file_key(row['entry'].path):
                    return att
            except FocusDeskError:
                pass
        return None

    def _writable(self):
        return (self.app.ws is self._ws and self._ws is not None and not self._ws.read_only
                and self.node_id in self._ws.nodes)

    def _manage_references(self):
        if self.app.ws is not self._ws or self.node_id not in self._ws.nodes: return
        ws, node_id = self._ws, self.node_id
        selected = ReferenceDialog(self, ws.get(node_id)).run()
        if not selected or not self._writable() or self._ws is not ws or self.node_id != node_id: return
        self._reference_id = selected
        try:
            att = self._selected_att()
            if att is None: return
            choices = [('remove', tr('ui.tab_files.elimina_doar_referinta'))]
            if att.mode == 'external': choices.insert(0, ('relocate', tr('ui.tab_files.relocalizeaza')))
            if att.mode == 'managed': choices.append(('delete', tr('ui.tab_files.sterge_copia_administrata_2')))
            choices.append(('cancel', tr('ui.meetings.anuleaza')))
            choice = ask_choice(self, att.name, tr('ui.tab_files.eliminarea_referintei_nu_sterge_fisierul_original'), choices)
            if choice == 'relocate': self._relocate()
            elif choice == 'remove': self._remove()
            elif choice == 'delete': self._remove_copy()
        finally:
            self._reference_id = None

    def _menu_state(self):
        writable = self._writable()
        for index in (6, 7, 8):
            self.menu.entryconfigure(index, state='normal' if writable else 'disabled')
        att = self._selected_att()
        self.menu.entryconfigure(9, state='normal' if writable and att and att.mode == 'external' else 'disabled')
        self.menu.entryconfigure(10, state='normal' if writable and att else 'disabled')
        self.menu.entryconfigure(11, state='normal' if writable and att and att.mode == 'managed' else 'disabled')

    def _context_menu(self, event):
        iid = self.tv.identify_row(event.y)
        if iid:
            if iid not in self.tv.selection(): self.tv.selection_set(iid)
            self.tv.focus(iid)
        self.menu.tk_popup(event.x_root, event.y_root)
        return 'break'

    def _keyboard_menu(self, _event):
        self.menu.tk_popup(self.tv.winfo_rootx()+20, self.tv.winfo_rooty()+30)
        return 'break'

    def _action(self, command, *, multiple=False, readable=False):
        selected = self.explorer.selected()
        if not selected or self._action_pending:
            return
        pairs = [(row['root'], row['entry'].path) for _, row in selected]
        if not multiple: pairs = pairs[:1]
        ws, node_id, generation = self._ws, self.node_id, self.explorer._generation
        self._action_serial += 1
        serial = self._action_serial
        self._action_pending = True

        def work(token):
            result = []
            for root, path in pairs:
                token.check()
                result.append(FileService.describe_entry(root, path, readable=readable))
            return result

        def done(entries):
            if serial != self._action_serial: return
            self._action_pending = False
            if self.app.ws is not ws or self.node_id != node_id or generation != self.explorer._generation:
                return
            try:
                command(entries)
            except (FocusDeskError, OSError) as exc:
                show_error(self, str(exc))

        def failed(error):
            if serial != self._action_serial: return
            self._action_pending = False
            if self.app.ws is ws and self.node_id == node_id and generation == self.explorer._generation:
                show_error(self, str(error))
                self.refresh()

        self.app.bridge.submit(work, done, failed, name='files-action')

    def _open(self):
        def opened(entries):
            path = entries[0].path
            if entries[0].is_dir:
                for iid, _row in self.explorer.selected()[:1]: self.explorer.open_directory(iid)
            elif system.is_runnable(path):
                choice = ask_choice(self, tr('ui.tab_files.script_executabil'),
                                    tr('ui.tab_files.nu_este_executat_de_focusdesk_alege_deschiderea_in_editor_sau_afisarea', path_name=path.name),
                                    [('editor', tr('ui.tab_files.deschide_in_vs_code')), ('explorer', tr('ui.tab_files.deschide_in_explorer')), ('cancel', tr('ui.meetings.anuleaza'))])
                if choice == 'editor': self._vscode()
                elif choice == 'explorer': self._reveal()
            else: system.open_with_default_app(path)
        self._action(opened, readable=True)

    def _reveal(self):
        self._action(lambda entries: system.reveal_in_explorer(entries[0].path))

    def _vscode(self):
        self._action(lambda entries: system.open_in_vscode(entries[0].path, self._ws.settings.vscode_path), readable=True)

    def _copy_path(self):
        def copied(entries):
            self.clipboard_clear(); self.clipboard_append('\n'.join(str(entry.path) for entry in entries))
            self.explorer.status.configure(text=tr('ui.tab_files.calea_a_fost_copiata'))
        self._action(copied, multiple=True)

    def _email(self):
        def attached(entries):
            if any(entry.is_dir for entry in entries):
                raise FocusDeskError(tr('ui.tab_files.selecteaza_documentele_din_interiorul_folderelor_directoarele_nu_sunt'))
            self.app.compose_mail(self.node_id, attachments=[entry.path for entry in entries])
        self._action(attached, multiple=True, readable=True)

    def _add(self) -> None:
        if not self._writable():
            return
        ws, node_id = self._ws, self.node_id
        res = AddAttachmentDialog(self).run()
        if not res or not self._writable() or self._ws is not ws or self.node_id != node_id:
            return
        mode, paths = res
        node_id = self.node_id
        if mode == "external":
            def add_all() -> None:
                for p in paths:
                    self.fs.add_external(node_id, p)
            if self.app.run_write(add_all, refresh=True):
                self.load(self.app.ws.get(node_id))
            return
        for p in paths:
            self._copy_one(node_id, p)

    def _copy_one(self, node_id: str, path: str, policy: str | None = None) -> None:
        fs = self.fs

        def work(tok):
            return fs.copy_managed(node_id, path, on_conflict=policy)

        def done(res) -> None:
            name, is_dir = res
            self.app.run_write(lambda: fs.register_managed(node_id, name, is_dir), refresh=True,
                               success_text=tr('ui.tab_files.copiat', name=name))
            if self.node_id == node_id:
                self.load(self.app.ws.get(node_id))

        def error(exc: BaseException) -> None:
            if isinstance(exc, NameConflict):
                ans = ask_choice(self, tr('ui.tab_files.nume_identic'),
                                 tr('ui.tab_files.exista_deja_in_fisierele_acestui_nod', exc_name=exc.name),
                                 [("keep_both", tr('ui.tab_files.pastreaza_ambele')), ("replace", tr('ui.tab_files.inlocuieste')), ("cancel", tr('ui.meetings.anuleaza'))])
                if ans in ("keep_both", "replace"):
                    self._copy_one(node_id, path, ans)
                return
            show_error(self, str(exc))

        self.app.run_job(work, done, on_error=error, name="copy-file", busy_text=tr('ui.tab_files.se_copiaza_fisierul'))

    def _relocate(self) -> None:
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        att = self._selected_att()
        if att is None or att.mode != "external":
            show_info(self, tr('ui.tab_files.doar_legaturile_externe_se_pot_relocaliza'))
            return
        p = filedialog.askdirectory(parent=self) if att.is_dir else filedialog.askopenfilename(parent=self)
        if self._ws is not ws or self.node_id != node_id or not self._writable(): return
        if p and self.app.run_write(lambda: self.fs.relocate(node_id, att.id, p), refresh=True):
            self.load(self.app.ws.get(self.node_id))  # type: ignore[arg-type]

    def _remove(self) -> None:
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        att = self._selected_att()
        if att is None:
            return
        if confirm(self, tr('ui.tab_files.elimini_doar_referinta_fisierul_nu_se_sterge_si_poate_ramane_vizibil_i', att_name=att.name)):
            if self._ws is not ws or self.node_id != node_id or not self._writable(): return
            if self.app.run_write(lambda: self.fs.remove_attachment(node_id, att.id), refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _remove_copy(self):
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        att = self._selected_att()
        if att is None or att.mode != 'managed': return
        choice = ask_choice(self, tr('ui.tab_files.sterge_copia_administrata'),
                            tr('ui.tab_files.stergi_fizic_copia_din_workspace_si_referinta_originalul_extern_nu_est', att_name=att.name),
                            [('delete', tr('ui.tab_files.sterge_copia_si_referinta')), ('cancel', tr('ui.meetings.anuleaza'))])
        if self._ws is not ws or self.node_id != node_id or not self._writable(): return
        if choice == 'delete' and self.app.run_write(lambda: self.fs.remove_attachment(node_id, att.id, delete_managed_copy=True), refresh=True):
            self.load(self.app.ws.get(self.node_id))

    # ---- code folder ------------------------------------------------
    def _set_code(self) -> None:
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        d = filedialog.askdirectory(parent=self, title=tr('ui.tab_files.alege_folderul_proiectului_de_lucru'))
        if self._ws is not ws or self.node_id != node_id or not self._writable(): return
        if d and self.app.run_write(lambda: self.fs.set_code_folder(node_id, d), refresh=True):
            self.load(self.app.ws.get(self.node_id))

    def _set_managed_code(self) -> None:
        if not self._writable():
            return
        ws, node_id = self._ws, self.node_id
        if confirm(self, tr('ui.tab_files.folosesc_folderul_administrat_existent_files_ca_folder_de_lucru_si_sur')):
            if self._ws is not ws or self.node_id != node_id or not self._writable(): return
            if self.app.run_write(lambda: self.fs.set_code_folder(node_id, "files", mode="managed"),
                                  refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _clear_code(self) -> None:
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        try: source = self.fs.effective_source(self.node_id)
        except FocusDeskError: source = None
        inherited = source is not None and source.inherited
        text = tr('ui.tab_files.opresc_mostenirea_folderului_pentru_acest_task_asocierea_proiectului_s') if inherited else tr('ui.tab_files.elimin_asocierea_proprie_fisierele_nu_se_sterg_o_sursa_mostenita_poate')
        if confirm(self, text):
            if self._ws is not ws or self.node_id != node_id or not self._writable(): return
            action = self.fs.disable_code_folder if inherited else self.fs.clear_code_folder
            if self.app.run_write(lambda: action(node_id), refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _code_explorer(self) -> None:
        self.app.open_code_in_explorer(self.node_id)

    def _code_vscode(self) -> None:
        self.app.open_code_in_vscode(self.node_id)
