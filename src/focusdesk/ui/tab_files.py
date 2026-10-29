"""Exploratorul folderelor reale, cu asocierile și referințele existente."""

from __future__ import annotations

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
        super().__init__(parent, "Legături și referințe existente", resizable=True, ok_text="Alege referința")
        self.geometry("740x400")
        self.minsize(520, 300)
        self.body.pack_forget()
        self.buttons.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        ttk.Label(self.body, text="Aceasta este lista referințelor salvate; exploratorul afișează separat discul real.",
                  style="Muted.TLabel", wraplength=440).pack(fill="x", pady=4)
        self.tv, frame = make_tree(self.body, [("name", "Nume", 170), ("mode", "Mod", 90), ("path", "Cale", 390)])
        frame.pack(fill="both", expand=True)
        for att in node.attachments:
            self.tv.insert("", "end", iid=att.id, values=(att.name, "Extern" if att.mode == "external" else "Administrat", att.path))
        self.tv.bind("<Return>", lambda _e: self._on_ok())
        self.tv.bind("<Double-1>", lambda _e: self._on_ok())

    def validate(self):
        return bool(self.tv.selection())

    def collect(self):
        return self.tv.selection()[0]


class AddAttachmentDialog(ModalDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Adaugă fișier sau folder", ok_text="Adaugă")
        self.mode = tk.StringVar(value="managed")
        self.paths: list[str] = []
        ttk.Radiobutton(self.body, variable=self.mode, value="managed",
                        text="Copie administrată (în workspace)").pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=440, text=(
            "Fișierul se copiază în folderul nodului (files/). Rămâne alături de task, intră în backup-ul complet "
            "și nu depinde de locul original.")).pack(anchor="w", padx=(22, 0), pady=(0, 8))
        ttk.Radiobutton(self.body, variable=self.mode, value="external",
                        text="Legătură externă (rămâne unde este)").pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=440, text=(
            "Se memorează doar calea. Nu se copiază nimic; dacă fișierul este mutat sau șters, legătura apare ca "
            "„Lipsește” și o poți relocaliza. Ștergerea legăturii nu șterge fișierul original.")).pack(
            anchor="w", padx=(22, 0), pady=(0, 8))
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Button(row, text="Alege fișiere…", command=self._pick_files).pack(side="left")
        ttk.Button(row, text="Alege folder…", command=self._pick_dir).pack(side="left", padx=6)
        self.summary = ttk.Label(self.body, text="Nimic ales", style="Muted.TLabel", wraplength=440)
        self.summary.pack(anchor="w", pady=(8, 0))

    def _pick_files(self) -> None:
        sel = filedialog.askopenfilenames(parent=self, title="Alege fișierele")
        if sel:
            self.paths = list(sel)
            self._summ()

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(parent=self, title="Alege folderul")
        if d:
            self.paths = [d]
            self._summ()

    def _summ(self) -> None:
        self.summary.configure(text="\n".join(self.paths[:6]) + (f"\n… și încă {len(self.paths) - 6}" if len(self.paths) > 6 else ""))

    def validate(self) -> bool:
        if not self.paths:
            show_error(self, "Alege cel puțin un fișier sau folder.")
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
        self.btn_add = ttk.Button(toolbar, text="Adaugă…", command=self._add)
        self.btn_add.pack(side="left")
        self.refresh_btn = ttk.Button(toolbar, text="Actualizează", command=self.refresh)
        self.refresh_btn.pack(side="left", padx=4)
        self.more = ttk.Menubutton(toolbar, text="Acțiuni")
        self.more.pack(side="left")
        self.menu = tk.Menu(self.more, tearoff=False)
        self.more.configure(menu=self.menu)
        for label, command in (("Deschide", self._open), ("Deschide în Explorer", self._reveal),
                               ("Deschide în VS Code", self._vscode), ("Copiază calea", self._copy_path),
                               ("Atașează la e-mail…", self._email)):
            self.menu.add_command(label=label, command=command)
        self.menu.add_separator()
        for label, command in (("Alege folderul proiectului…", self._set_code),
                               ("Folosește folderul administrat existent (files/)", self._set_managed_code),
                               ("Elimină asocierea / oprește moștenirea…", self._clear_code),
                               ("Relocalizează legătura…", self._relocate),
                               ("Elimină doar legătura/referința…", self._remove),
                               ("Șterge copia administrată și referința…", self._remove_copy)):
            self.menu.add_command(label=label, command=command)
        self.menu.add_command(label="Legături și referințe existente…", command=self._manage_references)
        if on_expand:
            self.menu.add_command(label="Mai mult spațiu pentru Fișiere", command=on_expand)
        self.menu.configure(postcommand=self._menu_state)
        self.code_lbl = ttk.Label(self, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.code_lbl.pack(fill="x", padx=8)
        self.path_tip = Tooltip(self.code_lbl, "Calea rădăcinii și a elementului selectat")
        self.code_note = ttk.Label(self, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.code_note.pack(fill="x", padx=8, pady=(2, 4))
        self.choose = ttk.Frame(self)
        ttk.Button(self.choose, text="Alege folderul proiectului…", command=self._set_code).pack(side="left")
        ttk.Button(self.choose, text="Folosește files/", command=self._set_managed_code).pack(side="left", padx=4)
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
                                'Folderul de lucru este indisponibil.' if work else 'Niciun folder de lucru asociat.')
        self.code_note.configure(text=(work.note or work.error) if work else 'Poți explora files/ sau asocia un folder extern, fără copiere.')
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
            self.path_tip.text = f"Rădăcină: {row['root']}\nSelectat: {path}"
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
            choices = [('remove', 'Elimină doar referința')]
            if att.mode == 'external': choices.insert(0, ('relocate', 'Relocalizează'))
            if att.mode == 'managed': choices.append(('delete', 'Șterge copia administrată…'))
            choices.append(('cancel', 'Anulează'))
            choice = ask_choice(self, att.name, 'Eliminarea referinței nu șterge fișierul original.', choices)
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
                choice = ask_choice(self, 'Script / executabil',
                                    f'„{path.name}” nu este executat de FocusDesk. Alege deschiderea în editor sau afișarea în Explorer.',
                                    [('editor', 'Deschide în VS Code'), ('explorer', 'Deschide în Explorer'), ('cancel', 'Anulează')])
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
            self.explorer.status.configure(text='Calea a fost copiată.')
        self._action(copied, multiple=True)

    def _email(self):
        def attached(entries):
            if any(entry.is_dir for entry in entries):
                raise FocusDeskError('Selectează documentele din interiorul folderelor. Directoarele nu sunt atașate sau arhivate automat.')
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
                               success_text=f"Copiat: {name}")
            if self.node_id == node_id:
                self.load(self.app.ws.get(node_id))

        def error(exc: BaseException) -> None:
            if isinstance(exc, NameConflict):
                ans = ask_choice(self, "Nume identic",
                                 f"Există deja „{exc.name}” în fișierele acestui nod.",
                                 [("keep_both", "Păstrează ambele"), ("replace", "Înlocuiește"), ("cancel", "Anulează")])
                if ans in ("keep_both", "replace"):
                    self._copy_one(node_id, path, ans)
                return
            show_error(self, str(exc))

        self.app.run_job(work, done, on_error=error, name="copy-file", busy_text="Se copiază fișierul…")

    def _relocate(self) -> None:
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        att = self._selected_att()
        if att is None or att.mode != "external":
            show_info(self, "Doar legăturile externe se pot relocaliza.")
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
        if confirm(self, f'Elimini doar referința „{att.name}”? Fișierul nu se șterge și poate rămâne vizibil în explorator, deoarece acesta arată discul real.'):
            if self._ws is not ws or self.node_id != node_id or not self._writable(): return
            if self.app.run_write(lambda: self.fs.remove_attachment(node_id, att.id), refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _remove_copy(self):
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        att = self._selected_att()
        if att is None or att.mode != 'managed': return
        choice = ask_choice(self, 'Șterge copia administrată',
                            f'Ștergi fizic copia „{att.name}” din workspace și referința? Originalul extern nu este șters.',
                            [('delete', 'Șterge copia și referința'), ('cancel', 'Anulează')])
        if self._ws is not ws or self.node_id != node_id or not self._writable(): return
        if choice == 'delete' and self.app.run_write(lambda: self.fs.remove_attachment(node_id, att.id, delete_managed_copy=True), refresh=True):
            self.load(self.app.ws.get(self.node_id))

    # ---- code folder ------------------------------------------------
    def _set_code(self) -> None:
        if not self._writable(): return
        ws, node_id = self._ws, self.node_id
        d = filedialog.askdirectory(parent=self, title="Alege folderul proiectului / de lucru")
        if self._ws is not ws or self.node_id != node_id or not self._writable(): return
        if d and self.app.run_write(lambda: self.fs.set_code_folder(node_id, d), refresh=True):
            self.load(self.app.ws.get(self.node_id))

    def _set_managed_code(self) -> None:
        if not self._writable():
            return
        ws, node_id = self._ws, self.node_id
        if confirm(self, "Folosesc folderul administrat existent files/ ca folder de lucru și sursă pentru checkpointuri? Fișierele nu se mută; sunt incluse în backupul complet."):
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
        text = "Opresc moștenirea folderului pentru acest task? Asocierea proiectului și fișierele nu se schimbă." if inherited else "Elimin asocierea proprie? Fișierele nu se șterg. O sursă moștenită poate redeveni disponibilă."
        if confirm(self, text):
            if self._ws is not ws or self.node_id != node_id or not self._writable(): return
            action = self.fs.disable_code_folder if inherited else self.fs.clear_code_folder
            if self.app.run_write(lambda: action(node_id), refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _code_explorer(self) -> None:
        self.app.open_code_in_explorer(self.node_id)

    def _code_vscode(self) -> None:
        self.app.open_code_in_vscode(self.node_id)
