"""The same profile settings component in Settings and nested mail composition."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import webbrowser

from ..i18n import tr
from ..integrations.gmail import GmailError
from .common import ModalDialog, ScrollFrame, confirm
from .design import wrap_actions


class EmailSettingsPanel(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app;self.pending=False
        settings=app.config.mail
        self.provider=tk.StringVar(value=tr('gmail.provider.'+settings.provider))
        self.address=tk.StringVar(value=settings.address)
        self.display_name=tk.StringVar(value=settings.display_name)
        self.password=tk.StringVar()
        self.remember=tk.BooleanVar(value=settings.remembered)
        self.feedback=ttk.Label(self,text='',style='Muted.TLabel',wraplength=650)
        self.feedback.pack(side='bottom',fill='x',pady=5)
        buttons=ttk.Frame(self);buttons.pack(side='bottom',fill='x',pady=5)
        self.controls=[]
        for key,command in (('save_settings',self.save),('test',self.test),('remove',self.remove)):
            button=ttk.Button(buttons,text=tr('gmail.'+key),command=command)
            button.pack(side='left',padx=(0,6));self.controls.append(button)
        wrap_actions(buttons)
        self.scroll=ScrollFrame(self);self.scroll.pack(fill='both',expand=True)
        form=self.scroll.inner
        for key,variable in (('default_provider',self.provider),('address',self.address),('display_name',self.display_name),('password',self.password)):
            ttk.Label(form,text=tr('gmail.'+key)).pack(anchor='w',pady=(8,2))
            if key=='default_provider':
                self.provider_box=ttk.Combobox(form,textvariable=variable,state='readonly',values=[tr('gmail.provider.outlook'),tr('gmail.provider.gmail')])
                widget=self.provider_box
            else:widget=ttk.Entry(form,textvariable=variable,show='•' if key=='password' else '')
            if key=='password':self.password_entry=widget
            widget.pack(fill='x');self.controls.append(widget)
        self.remember_box=ttk.Checkbutton(form,text=tr('gmail.remember'),variable=self.remember)
        self.remember_box.pack(anchor='w',pady=8);self.controls.append(self.remember_box)
        self.explanation=ttk.Label(form,text=tr('gmail.explanation'),wraplength=650,justify='left')
        self.explanation.pack(fill='x',pady=8)
        help_button=ttk.Button(form,text=tr('gmail.password_help'),style='Quiet.TButton',command=self.password_help)
        help_button.pack(anchor='w')
        self.storage_notice=ttk.Label(form,text=tr('gmail.secure_storage') if app.gmail.store.available else tr('gmail.session_only'),wraplength=650,style='Muted.TLabel')
        self.storage_notice.pack(fill='x',pady=8)
        self.bind('<Configure>',lambda e:[w.configure(wraplength=max(220,e.width-28)) for w in (self.feedback,self.explanation,self.storage_notice)])
        for widget in [*self.controls,help_button]:
            widget.bind('<FocusIn>',self._reveal_focus,add='+')
            widget.bind('<Return>',lambda event,w=widget:self._activate(w))

    def _activate(self,widget):
        # The parent Settings dialog binds Return to workspace Save. Mail profile
        # fields must never trigger that unrelated save or silently close this form.
        if isinstance(widget,ttk.Button) and not widget.instate(['disabled']):widget.invoke()
        return 'break'

    def _reveal_focus(self,event):
        if not str(event.widget).startswith(str(self.scroll)):return
        canvas=self.scroll.canvas
        y=event.widget.winfo_rooty()-self.scroll.inner.winfo_rooty()
        bottom=y+event.widget.winfo_height();top=canvas.canvasy(0)
        height=max(1,self.scroll.inner.winfo_height())
        if y<top:canvas.yview_moveto(y/height)
        elif bottom>top+canvas.winfo_height():canvas.yview_moveto((bottom-canvas.winfo_height())/height)

    def password_help(self):
        webbrowser.open('https://myaccount.google.com/apppasswords')

    def _busy(self,value):
        self.pending=value
        for widget in self.controls:widget.configure(state='disabled' if value else 'normal')
        if not value:self.provider_box.configure(state='readonly')

    def save(self):
        if self.pending:return False
        try:
            provider=('outlook','gmail')[self.provider_box.current()]
            text=self.app.gmail.configure(provider=provider,address=self.address.get(),display_name=self.display_name.get(),password=self.password.get(),remember=self.remember.get())
        except GmailError as exc:self.feedback.configure(text=str(exc));return False
        self.password.set('')
        self.remember.set(self.app.config.mail.remembered)
        self.feedback.configure(text=text)
        return True

    def test(self):
        if self.pending:return
        try:credentials=self.app.gmail.credentials(address=self.address.get(),display_name=self.display_name.get(),password=self.password.get())
        except GmailError as exc:self.feedback.configure(text=str(exc));return
        self._busy(True);self.feedback.configure(text=tr('gmail.testing'))
        def finish(value):
            if not self.winfo_exists():return
            self._busy(False)
            self.feedback.configure(text=tr('gmail.test_ok') if value is True else str(value))
        self.app.gmail.test(credentials,finish,finish)

    def remove(self):
        if self.pending or not confirm(self,tr('gmail.remove_confirm')):return
        try:self.app.gmail.remove()
        except GmailError as exc:self.feedback.configure(text=str(exc));return
        self.password.set('');self.address.set('');self.display_name.set('');self.remember.set(False)
        self.provider_box.current(0);self.feedback.configure(text=tr('gmail.removed'))

    def destroy(self):
        self.password.set('')
        super().destroy()


class EmailSettingsDialog(ModalDialog):
    enter_confirms=False
    def __init__(self,parent,app):
        super().__init__(parent,tr('gmail.settings_title'),resizable=True,ok_text=tr('ui.outlook_ui.inchide'))
        self.geometry('780x620');self.minsize(600,360)
        self.cancel_btn.pack_forget()
        self.body.pack_forget();self.buttons.pack_forget()
        self.buttons.pack(side='bottom',fill='x')
        self.body.pack(fill='both',expand=True)
        self.panel=EmailSettingsPanel(self.body,app);self.panel.pack(fill='both',expand=True)

    def run(self):
        previous,focus=self.grab_current(),self.focus_get()
        try:return super().run()
        finally:
            if previous is not None and previous.winfo_exists():previous.grab_set()
            if focus is not None and focus.winfo_exists():focus.focus_set()
