"""Disposable guided-description draft; no persistence, parsing or task mutations."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from .common import ScrollFrame
from .design import C, px

APPLIED_MESSAGE = 'Aplicat în descriere. Salvează taskul pentru păstrare.'


def guided_text(goal, steps, result):
    """Keep field contents verbatim; skip whitespace-only fields and number real steps."""
    sections = []
    if goal.strip(): sections.append('Scop\n' + goal)
    for number, content in enumerate((text for text in steps if text.strip()), 1):
        sections.append(f'Pasul {number}\n' + content)
    if result.strip(): sections.append('Rezultat așteptat\n' + result)
    if not sections:
        raise ValueError('Completează cel puțin o secțiune: Scop, un pas sau Rezultat așteptat.')
    return '\n\n'.join(sections)


def append_description(existing, generated):
    if not existing: return generated
    separator = '' if existing.endswith('\n\n') else '\n' if existing.endswith('\n') else '\n\n'
    return existing + separator + generated


class NestedModal(tk.Toplevel):
    """Local grab/focus stack, also safe when called from an existing modal editor."""
    def __init__(self, parent):
        self.previous_grab = parent.grab_current()
        self.previous_focus = parent.focus_get()
        self.previous_grab_status = self.previous_grab.grab_status() if self.previous_grab else None
        super().__init__(parent)
        self.transient(parent.winfo_toplevel())
        self.bind('<Control-s>', lambda event: 'break')
        self._closed = False

    def close_modal(self, focus=None):
        if self._closed: return
        self._closed = True
        previous, status = self.previous_grab, self.previous_grab_status
        target = focus or self.previous_focus
        if self.grab_current() is self: self.grab_release()
        self.destroy()
        try:
            if previous is not None and previous.winfo_exists():
                if status == 'global': previous.grab_set_global()
                else: previous.grab_set()
            if target is not None and target.winfo_exists(): target.focus_set()
        except tk.TclError:
            pass  # The originating task/window may have been closed externally.


class ExistingDescriptionChoice(NestedModal):
    def __init__(self, guide, generated, expected):
        super().__init__(guide)
        self.guide, self.generated, self.expected = guide, generated, expected
        self.title('Descriere existentă')
        self.resizable(True, True)
        self._focusdesk_sized = True
        self.geometry(f'{px(self,680)}x{px(self,210)}')
        self.minsize(px(self,440), px(self,190))
        self.columnconfigure(0,weight=1); self.rowconfigure(0,weight=1)
        self.prompt=ttk.Label(self, text='Descrierea conține deja text. Cum aplici conținutul ghidului?',
                  style='Section.TLabel', wraplength=px(self,600), padding=16)
        self.prompt.grid(row=0,column=0,sticky='nsew')
        self.bind('<Configure>',lambda event:self.prompt.configure(wraplength=max(180,self.winfo_width()-40)))
        bar=ttk.Frame(self,padding=12);bar.grid(row=1,column=0,sticky='ew')
        bar.columnconfigure(0,weight=1);bar.columnconfigure(1,weight=1)
        self.append_btn=ttk.Button(bar,text='Adaugă la final',style='Primary.TButton',command=lambda:self.choose('append'))
        self.append_btn.grid(row=0,column=0,sticky='ew',padx=(0,6))
        self.replace_btn=ttk.Button(bar,text='Înlocuiește descrierea',command=lambda:self.choose('replace'))
        self.replace_btn.grid(row=0,column=1,sticky='ew')
        self.cancel_btn=ttk.Button(bar,text='Anulează',command=self.cancel)
        self.cancel_btn.grid(row=1,column=0,columnspan=2,pady=(8,0))
        for button,mode in ((self.append_btn,'append'),(self.replace_btn,'replace')):
            button.bind('<Return>',lambda event,m=mode:self.choose(m))
        self.cancel_btn.bind('<Return>',self.cancel)
        self.bind('<Return>',lambda event:self.choose('append'))
        self.bind('<Escape>',self.cancel)
        self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.grab_set();self.append_btn.focus_set()

    def choose(self, mode):
        self.guide.choice = None
        self.close_modal(focus=self.guide.apply_btn)
        self.guide.finish_apply(mode,self.generated,self.expected)
        return 'break'

    def cancel(self,event=None):
        self.guide.choice = None
        self.close_modal(focus=self.guide.apply_btn)
        return 'break'


class StepField(ttk.Frame):
    def __init__(self, guide):
        super().__init__(guide.steps_frame,style='Card.TFrame',padding=8)
        self.guide=guide
        head=ttk.Frame(self);head.pack(fill='x')
        self.label=ttk.Label(head,style='Section.TLabel');self.label.grid(row=0,column=0,sticky='w');head.columnconfigure(0,weight=1)
        self.up=ttk.Button(head,text='Sus',command=lambda:guide.move_step(self,-1));self.up.grid(row=0,column=1,padx=3)
        self.down=ttk.Button(head,text='Jos',command=lambda:guide.move_step(self,1));self.down.grid(row=0,column=2,padx=3)
        ttk.Button(head,text='Șterge pasul',command=lambda:guide.remove_step(self)).grid(row=0,column=3,padx=(3,0))
        self.text=guide.text_field(self,height=3)


class DescriptionGuide(NestedModal):
    def __init__(self, editor, context):
        super().__init__(editor)
        self.editor,self.context=editor,context
        self.choice=None;self.steps=[]
        self.title('Completează descrierea cu ghid')
        self._focusdesk_sized=True
        width=min(px(self,760),self.winfo_screenwidth()-40)
        height=min(px(self,680),self.winfo_screenheight()-80)
        self.geometry(f'{width}x{height}')
        self.minsize(min(px(self,500),width),min(px(self,360),height));self.resizable(True,True)
        header=ttk.Frame(self,padding=(14,12));header.pack(fill='x')
        ttk.Label(header,text='Completează descrierea',style='Title.TLabel').pack(anchor='w')
        ttk.Label(header,text='Ciornă separată. Pașii sunt text, nu checklist sau subtaskuri.',style='Muted.TLabel',wraplength=px(self,650)).pack(anchor='w',pady=(4,0))
        # Footer is outside the scrolling form and always remains accessible.
        footer=ttk.Frame(self,padding=(12,8));footer.pack(side='bottom',fill='x');footer.columnconfigure(0,weight=1)
        self.error=ttk.Label(footer,text='',foreground=C.danger,wraplength=px(self,650));self.error.grid(row=0,column=0,columnspan=3,sticky='ew',pady=(0,6))
        ttk.Button(footer,text='+ Adaugă pas',command=self.add_step).grid(row=1,column=0,sticky='w',padx=(0,6))
        self.apply_btn=ttk.Button(footer,text='Aplică în descriere',style='Primary.TButton',command=self.apply)
        self.apply_btn.grid(row=1,column=1,padx=(0,6))
        ttk.Button(footer,text='Anulează',command=self.cancel).grid(row=1,column=2)
        self.sf=ScrollFrame(self);self.sf.pack(fill='both',expand=True,padx=12)
        self.goal=self.section(self.sf.inner,'Scop')
        self.steps_frame=ttk.Frame(self.sf.inner);self.steps_frame.pack(fill='x')
        self.add_step(focus=False);self.add_step(focus=False)
        self.result=self.section(self.sf.inner,'Rezultat așteptat')
        self.bind('<Configure>',lambda event:self.error.configure(wraplength=max(220,self.winfo_width()-32)))
        self.bind('<Escape>',self.cancel);self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.grab_set();self.goal.focus_set()

    def section(self,parent,title):
        frame=ttk.Frame(parent,padding=(8,8));frame.pack(fill='x',pady=(0,8))
        ttk.Label(frame,text=title,style='Section.TLabel').pack(anchor='w')
        return self.text_field(frame,height=4)

    def text_field(self,parent,*,height):
        frame=ttk.Frame(parent);frame.pack(fill='x',pady=(4,0))
        text=tk.Text(frame,height=height,width=30,wrap='word',undo=True,autoseparators=True,
                     font=(self._root()._focusdesk_family,10))
        text.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(frame,command=text.yview);bar.pack(side='right',fill='y');text.configure(yscrollcommand=bar.set)
        text.bind('<Control-a>',lambda event:self.select_all(text))
        return text

    @staticmethod
    def select_all(text):
        text.tag_add('sel','1.0','end-1c');return 'break'

    def add_step(self,*,focus=True):
        field=StepField(self);self.steps.append(field);self.render_steps()
        if focus:
            field.text.focus_set()
            self.update_idletasks()
            self.sf.canvas.yview_moveto((self.steps_frame.winfo_y()+field.winfo_y())/max(1,self.sf.inner.winfo_reqheight()))
        return field

    def move_step(self,field,delta):
        index=self.steps.index(field);target=index+delta
        if 0<=target<len(self.steps):
            self.steps[index],self.steps[target]=self.steps[target],self.steps[index]
            self.render_steps();field.text.focus_set()

    def remove_step(self,field):
        index=self.steps.index(field);self.steps.remove(field);field.destroy();self.render_steps()
        (self.steps[min(index,len(self.steps)-1)].text if self.steps else self.goal).focus_set()

    def render_steps(self):
        for field in self.steps:field.pack_forget()
        for index,field in enumerate(self.steps):
            field.label.configure(text=f'Pasul {index+1}')
            field.up.state(['disabled'] if index==0 else ['!disabled'])
            field.down.state(['disabled'] if index==len(self.steps)-1 else ['!disabled'])
            field.pack(fill='x',pady=(0,8))

    def can_apply(self):
        if not self.editor.winfo_exists() or self.editor.read_only or self.editor.guide_context() != self.context:
            self.error.configure(text='Taskul nu mai este disponibil, contextul s-a schimbat sau este doar pentru citire. Ciorna ghidului nu a fost aplicată.')
            return False
        return True

    def apply(self):
        if self.choice is not None:
            self.choice.lift();return False
        if not self.can_apply():return False
        try:
            text=guided_text(self.goal.get('1.0','end-1c'),[f.text.get('1.0','end-1c') for f in self.steps],self.result.get('1.0','end-1c'))
        except ValueError as exc:
            self.error.configure(text=str(exc));self.goal.focus_set();return False
        existing=self.editor.get()
        if existing:
            self.choice=ExistingDescriptionChoice(self,text,existing)
            return False
        return self.finish_apply('replace',text,existing)

    def finish_apply(self,mode,text,expected):
        if not self.can_apply():return False
        if self.editor.get()!=expected:
            self.error.configure(text='Descrierea s-a schimbat între timp. Aplică din nou și alege cum păstrezi textul actual.')
            return False
        if mode not in ('append','replace'):return False
        value=append_description(expected,text) if mode=='append' else text
        self.editor.replace('1.0','end-1c',value)
        self.editor.show_guide_notice(APPLIED_MESSAGE)
        self.close(applied=True)
        return True

    def cancel(self,event=None):
        self.close();return 'break'

    def close(self,*,applied=False):
        if self.choice is not None:self.choice.cancel()
        self.editor.guide_dialog=None
        self.close_modal(focus=self.editor.text if applied else None)
