"""Editable mail snapshot kept alive until Outlook returns; never saves task fields."""
from __future__ import annotations

from ..i18n import tr

import tkinter as tk
from tkinter import filedialog, ttk

from ..errors import FocusDeskError, ValidationError
from ..integrations.outlook import MailHandoffUncertain
from ..services.colleagues import requester
from ..services.files import FileService
from ..services.mail import (attachment_selection, attachment_summary, build_draft, confirmation_text,
                             default_body, default_subject, format_size)
from ..workers.com_worker import ComTimeout
from .common import ModalDialog, ScrollFrame, Tooltip, confirm, make_tree, show_error, show_info
from .colleagues_ui import ColleaguePickerDialog
from .file_picker import TaskFilePicker


class DescriptionSourceDialog(ModalDialog):
    """Enter defaults to the current shared editor buffer; no task fields are saved."""
    def __init__(self, parent):
        super().__init__(parent, tr('ui.mail_ui.descriere_nesalvata'), ok_text=tr('ui.mail_ui.foloseste_descrierea_curenta'))
        ttk.Label(self.body, wraplength=520, justify="left", text=(
            tr('ui.mail_ui.descrierea_are_modificari_nesalvate_ce_versiune_introduc_in_e_mail_ale'))).pack(fill="x")
        ttk.Button(self.body, text=tr('ui.mail_ui.foloseste_ultima_versiune_salvata'), command=self._saved).pack(anchor="w", pady=10)

    def _saved(self):
        self.result = "saved"
        self.destroy()

    def collect(self):
        return "current"

    def run(self):
        previous, focus = self.grab_current(), self.focus_get()
        try:
            return super().run()
        finally:
            if previous is not None and previous.winfo_exists():
                previous.grab_set()
            if focus is not None and focus.winfo_exists():
                focus.focus_set()


class MailDialog(ModalDialog):
    enter_confirms = False  # Enter in a field never submits the form.

    def __init__(self, parent, app, node, *, description=None):
        super().__init__(parent, tr('ui.mail_ui.e_mail_din_task'), resizable=True, ok_text=tr('ui.mail_ui.trimite'), cancel_text=tr('ui.outlook_ui.inchide'))
        self.app, self.ws, self.node_id = app, app.ws, node.id
        self.action = "send"
        self.pending = False
        self.uncertain = False
        self.attachments = []
        self._controls = [self.ok_btn, self.cancel_btn]
        self.geometry("860x730")
        self.minsize(680, 540)
        self.draft_btn = ttk.Button(self.buttons, text=tr('ui.mail_ui.deschide_ciorna_in_outlook'), command=self._open_draft)
        self.draft_btn.pack(side="left")
        self._controls.append(self.draft_btn)
        self.cancel_btn.configure(command=self._cancel)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.body.pack_forget()
        self.buttons.pack_forget()
        self.buttons.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        self.feedback = ttk.Frame(self, padding=(16, 2))
        self.feedback_scroll = ScrollFrame(self.feedback)
        self.feedback_scroll.canvas.configure(height=64)
        self.feedback_scroll.pack(fill="x")
        self.form = ScrollFrame(self.body)
        self.form.pack(fill="both", expand=True)
        b = self.form.inner
        b.columnconfigure(1, weight=1)
        b.rowconfigure(4, weight=1)
        self.task_label = ttk.Label(b, text=tr('ui.mail_ui.task', node_title=node.title), style="Section.TLabel", wraplength=720)
        self.task_label.grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.to_var, self.cc_var = tk.StringVar(), tk.StringVar()
        person = node.requested_by
        try:
            person = requester(self.ws, node)
        except FocusDeskError as exc:
            show_error(self, str(exc))
        if person:
            self.to_var.set(person.email)
        self.subject_var = tk.StringVar(value=default_subject(node))
        for r, (label, var) in enumerate(((tr('ui.mail_ui.catre'), self.to_var), ("CC", self.cc_var), (tr('ui.mail_ui.subiect'), self.subject_var)), 1):
            ttk.Label(b, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            line = ttk.Frame(b)
            line.grid(row=r, column=1, sticky="ew", pady=4)
            entry = ttk.Entry(line, textvariable=var)
            entry.pack(side="left", fill="x", expand=True)
            self._controls.append(entry)
            if r in (1, 2):
                pick = ttk.Button(line, text="…", width=3, command=lambda target=var: self._add_colleague(target))
                pick.pack(side="left", padx=(4, 0))
                self._controls.append(pick)
                Tooltip(pick, tr('ui.mail_ui.adauga_un_coleg'))
            if r == 1:
                self.to_entry = entry
        ttk.Label(b, text=tr('ui.mail_ui.mesaj')).grid(row=4, column=0, sticky="nw", pady=4, padx=(0, 10))
        wrap = ttk.Frame(b)
        wrap.grid(row=4, column=1, sticky="nsew", pady=4)
        self.text = tk.Text(wrap, wrap="word", height=8, width=20, font="TkTextFont", undo=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.text.insert("1.0", default_body(self.ws, node, description=description))
        self._controls.append(self.text)
        attachments = ttk.LabelFrame(b, text=tr('ui.mail_ui.atasamente'), padding=6)
        attachments.grid(row=5, column=0, columnspan=2, sticky="ew", pady=6)
        for col in range(2):
            attachments.columnconfigure(col, weight=1)
        for col, (label, command) in enumerate(((tr('ui.mail_ui.adauga_fisiere'), self._add_files),
                                                (tr('ui.mail_ui.din_fisierele_taskului_proiectului'), self._from_task))):
            button = ttk.Button(attachments, text=label, command=command)
            button.grid(row=0, column=col, sticky="w", padx=2)
            self._controls.append(button)
        self.attachment_tree, frame = make_tree(attachments, [
            ("name", tr('ui.file_picker.nume'), 170), ("size", tr('ui.file_picker.dimensiune'), 95), ("state", tr('ui.meetings.stare'), 95), ("path", tr('ui.dashboard.locatie'), 340)], height=3)
        self.attachment_tree.configure(selectmode="extended")
        frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        self.attachment_tree.bind("<Delete>", lambda _e: self._remove_attachments())
        remove = ttk.Button(attachments, text=tr('ui.mail_ui.elimina_din_e_mail'), command=self._remove_attachments)
        remove.grid(row=2, column=0, sticky="w")
        self._controls.append(remove)
        self.attachment_count = ttk.Label(attachments, text=attachment_summary([]), style="Muted.TLabel")
        self.attachment_count.grid(row=2, column=1, sticky="e")
        self.attachment_path = ttk.Label(attachments, text="", style="Muted.TLabel", wraplength=720)
        self.attachment_path.grid(row=3, column=0, columnspan=2, sticky="w")
        self.attachment_tree.bind("<<TreeviewSelect>>", self._selected_attachment)
        self.help_label = ttk.Label(b, style="Muted.TLabel", wraplength=740, justify="left", text=(
            tr('ui.mail_ui.adrese_separate_prin_sau_contul_implicit_outlook_classic_mesaj_nou_far')))
        self.help_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.message = ttk.Label(self.feedback_scroll.inner, text="", style="Muted.TLabel", wraplength=740, justify="left")
        self.message.pack(fill="x")
        self.checked_btn = ttk.Button(self.feedback, text=tr('ui.mail_ui.am_verificat_in_outlook'), command=self._checked_outlook)
        self.bind("<Configure>", self._resize)
        for widget in [*self._controls, self.attachment_tree]:
            widget.bind("<FocusIn>", self._reveal_focus, add="+")
        self.to_entry.focus_set()

    def _resize(self, event):
        if event.widget is self:
            for label in (self.message, self.attachment_path, self.task_label, self.help_label):
                label.configure(wraplength=max(300, event.width - 75))

    def _reveal_focus(self, event):
        widget = event.widget
        if not str(widget).startswith(str(self.form)):
            return
        canvas = self.form.canvas
        y = widget.winfo_rooty() - self.form.inner.winfo_rooty()
        bottom = y + widget.winfo_height()
        top = canvas.canvasy(0)
        height = max(1, self.form.inner.winfo_height())
        if y < top:
            canvas.yview_moveto(y / height)
        elif bottom > top + canvas.winfo_height():
            canvas.yview_moveto((bottom - canvas.winfo_height()) / height)

    def _set_message(self, text, *, error=False):
        self.message.configure(text=text)
        self.feedback_scroll.canvas.configure(height=80 if error else 30)
        self.feedback.pack(side="bottom", fill="x", before=self.body)
        self.feedback_scroll.canvas.yview_moveto(0)

    def _valid_context(self):
        if self.app.ws is not self.ws or self.node_id not in self.ws.nodes:
            return False
        try:
            return (self.ws.node_dir(self.node_id) / "node.json").is_file()
        except (OSError, FocusDeskError):
            return False

    def _add_colleague(self, target):
        if self.pending:
            return
        person = ColleaguePickerDialog(self, self.ws).run()
        if self.winfo_exists():
            self.grab_set()
        if person is not None:
            current = target.get().strip().rstrip(";,")
            target.set(f"{current}; {person.email}" if current else person.email)

    def _add_files(self):
        if not self.pending:
            self._select_attachments(filedialog.askopenfilenames(parent=self, title=tr('ui.mail_ui.ataseaza_fisiere_la_e_mail')))

    def _from_task(self):
        if self.pending:
            return
        if not self._valid_context():
            show_error(self, tr('ui.mail_ui.taskul_sau_workspace_ul_nu_mai_este_disponibil'))
            return
        paths = TaskFilePicker(self, FileService(self.ws), self.node_id).run()
        if paths:
            self._select_attachments(paths)

    def _select_attachments(self, paths):
        if self.pending:
            return
        self.attachments = attachment_selection([*self.attachments, *paths])
        self._render_attachments()
        invalid = [item for item in self.attachments if item.state != "ready"]
        if invalid:
            self._set_message(tr('ui.mail_ui.unele_atasamente_nu_sunt_disponibile_elimina_le_sau_restabileste_acces'))

    def _render_attachments(self):
        selected = self.attachment_tree.selection()
        self.attachment_tree.delete(*self.attachment_tree.get_children())
        states = {"ready": tr('ui.mail_ui.disponibil'), "missing": tr('ui.mail_ui.lipseste'), "inaccessible": tr('ui.mail_ui.inaccesibil'), "directory": tr('ui.file_picker.folder')}
        for i, item in enumerate(self.attachments):
            self.attachment_tree.insert("", "end", iid=str(i), values=(
                item.name, format_size(item.size_bytes) if item.size_bytes is not None else "—", states[item.state], item.path))
        self.attachment_count.configure(text=attachment_summary(self.attachments))
        self.attachment_tree.selection_set([key for key in selected if self.attachment_tree.exists(key)])

    def _selected_attachment(self, _event=None):
        selected = self.attachment_tree.selection()
        item = self.attachments[int(selected[0])] if selected else None
        self.attachment_path.configure(text=f"{item.path} {item.detail}" if item else "")

    def _remove_attachments(self):
        if self.pending:
            return
        selected = {int(key) for key in self.attachment_tree.selection()}
        self.attachments = [item for i, item in enumerate(self.attachments) if i not in selected]
        self._render_attachments()

    def _build(self):
        self.attachments = attachment_selection(self.attachments)
        self._render_attachments()
        return build_draft(self.to_var.get(), self.cc_var.get(), self.subject_var.get(),
                           self.text.get("1.0", "end-1c"), for_send=self.action == "send", attachments=self.attachments)

    def validate(self):
        if not self._valid_context():
            show_error(self, tr('ui.mail_ui.taskul_sau_workspace_ul_nu_mai_este_disponibil_mesajul_ramane_in_formu'), "E-mail")
            return False
        try:
            self._validated_draft = self._build()
        except ValidationError as exc:
            show_error(self, str(exc), "E-mail")
            return False
        return self.action != "send" or confirm(self, confirmation_text(self._validated_draft), tr('ui.mail_ui.trimite_e_mail'))

    def collect(self):
        return {"action": self.action, "draft": self._build()}

    def _on_ok(self):
        self._submit("send")

    def _open_draft(self):
        self._submit("draft")

    def _busy(self, busy):
        for widget in self._controls:
            widget.configure(state="disabled" if busy else "normal")

    def _submit(self, action):
        if self.pending or self.uncertain:
            return
        self.pending, self.action = True, action
        self._busy(True)
        try:
            if not self.validate():
                self.pending = False
                self._busy(False)
                return
            draft = self._validated_draft
            self._set_message(tr('ui.mail_ui.se_asteapta_outlook_mesajul_si_atasamentele_raman_in_formular'))
            self.app.outlook.send_mail(draft, action == "send",
                                      lambda result: self._completed(draft, result),
                                      lambda error: self._failed(draft, error))
        except Exception as exc:
            self._failed(None, exc)

    def _completed(self, draft, result):
        # Logging failure cannot turn a confirmed handoff into a transport retry.
        try:
            notice = self.app.record_mail_result(self.ws, self.node_id, draft, result)
        except Exception as exc:
            notice = tr('ui.mail_ui.rezultatul_outlook_este_confirmat_dar_jurnalul_local_nu_a_putut_fi_scr', exc=exc)
        self.app.status.set_message(tr('ui.mail_ui.ciorna_deschisa_in_outlook') if result == "displayed" else
                                    tr('ui.mail_ui.e_mail_predat_outlook_livrare_neconfirmata'))
        self.pending = False
        self.result = {"action": self.action, "draft": draft, "result": result}
        self.destroy()
        show_info(self.app.root, notice, "E-mail")

    def _failed(self, draft, error):
        if not self.winfo_exists():
            return
        self.pending = False
        self._busy(False)
        self.attachments = attachment_selection(self.attachments)
        self._render_attachments()
        self.uncertain = isinstance(error, (ComTimeout, MailHandoffUncertain))
        text = str(error)
        if self.uncertain:
            text += (tr('ui.mail_ui.rezultatul_este_incert_mesajul_poate_fi_deja_in_outlook_verifica_feres'))
            self.ok_btn.configure(state="disabled")
            self.draft_btn.configure(state="disabled")
            self.checked_btn.pack(anchor="w", pady=4)
            if draft is not None:
                try:
                    self.app.record_mail_result(self.ws, self.node_id, draft, "uncertain")
                except Exception:
                    pass
        else:
            text += tr('ui.mail_ui.formularul_este_pastrat_corecteaza_problema_si_incearca_din_nou')
        self._set_message(text, error=True)

    def _checked_outlook(self):
        if confirm(self, tr('ui.mail_ui.ai_verificat_in_outlook_ca_nu_exista_deja_ciorna_sau_mesajul_predat_pe'), tr('ui.mail_ui.reincercare_explicita')):
            self.uncertain = False
            self.checked_btn.pack_forget()
            self.ok_btn.configure(state="normal")
            self.draft_btn.configure(state="normal")
            self._set_message(tr('ui.mail_ui.poti_reincerca_explicit_dupa_verificarea_in_outlook'))

    def _cancel(self):
        if not self.pending:
            self.destroy()

    def run(self):
        previous, focus = self.grab_current(), self.focus_get()
        try:
            return super().run()
        finally:
            if previous is not None and previous.winfo_exists():
                previous.grab_set()
            if focus is not None and focus.winfo_exists():
                focus.focus_set()
