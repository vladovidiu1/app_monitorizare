"""Single-field description editing with a shared Tk text buffer."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, simpledialog

STRUCTURED = '''## Obiectiv

## Context

## Pași / cerințe

- 

## Rezultat așteptat

## Criterii de finalizare

## Observații
'''
LIST = re.compile(r'^(\s*)([-+*]|\d+[.)])\s+(\[[ xX]\]\s+)?(.*)$')


class PeerText(tk.Text):
    """A second view of the SAME Tcl document, including its undo history."""
    def __init__(self, parent, source):
        # Register a Python widget wrapper, then create the Tcl peer at its path.
        tk.Widget._setup(self, parent, {})
        self.tk = parent.tk
        self._tclCommands = []
        source.tk.call(source._w, 'peer', 'create', self._w)


class MarkdownEditor(ttk.Frame):
    def __init__(self, parent, *, on_change=lambda: None, on_save=lambda: None, source=None, expand=None):
        super().__init__(parent, padding=6)
        self.on_change, self.on_save = on_change, on_save
        self.read_only = False
        heading = ttk.Frame(self)
        heading.pack(fill='x')
        ttk.Label(heading, text='Descriere', style='Section.TLabel').pack(side='left')
        self.expand_btn = None
        if expand:
            self.expand_btn = ttk.Button(heading, text='Extinde descrierea', command=expand)
            self.expand_btn.pack(side='right')
        edit = ttk.Frame(self)
        edit.pack(fill='both', expand=True, pady=(4, 0))
        self.text = PeerText(edit, source) if source is not None else tk.Text(edit, undo=True, autoseparators=True)
        self.text.configure(wrap='word', height=10, width=20, font=(self._root()._focusdesk_family, 10), padx=8, pady=8, exportselection=False)
        self.text.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(edit, command=self.text.yview)
        sb.pack(side='right', fill='y')
        self.text.configure(yscrollcommand=sb.set)
        self.text.bind('<<Modified>>', self._modified)
        self.text.bind('<Control-z>', lambda e: self.undo())
        self.text.bind('<Control-y>', lambda e: self.redo())
        self.text.bind('<Control-Shift-Z>', lambda e: self.redo())
        self.text.bind('<Control-a>', self.select_all)
        self.text.bind('<Control-s>', lambda e: self.save())

    def save(self):
        self.on_save()
        return 'break'

    def get(self):
        return self.text.get('1.0', 'end-1c')

    def _modified(self, event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.on_change()

    def set_read_only(self, value):
        self.read_only = value
        self.text.configure(state='disabled' if value else 'normal')
        for button in ([self.expand_btn] if self.expand_btn else []):
            button.state(['disabled'] if value else ['!disabled'])

    def select_all(self, event=None):
        self.text.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def bounds(self):
        try:
            return self.text.index('sel.first'), self.text.index('sel.last')
        except tk.TclError:
            return self.text.index('insert'), self.text.index('insert')

    def replace(self, start, end, value):
        if self.read_only:
            return
        self.text.edit_separator()
        self.text.replace(start, end, value)
        self.text.mark_set('insert', f'{start}+{len(value)}c')
        self.text.edit_separator()
        self.text.focus_set()
        self.on_change()

    def wrap(self, before, after):
        if not self.read_only:
            a, b = self.bounds()
            value = self.text.get(a, b)
            self.replace(a, b, before + value + after)
            self.text.tag_remove('sel', '1.0', 'end')
            self.text.tag_add('sel', f'{a}+{len(before)}c', f'{a}+{len(before)+len(value)}c')
            self.text.mark_set('insert', f'{a}+{len(before)+len(value)}c')
        return 'break'

    def line_bounds(self):
        a, b = self.bounds()
        if self.text.compare(a, '!=', b) and b.endswith('.0'):
            b = self.text.index(f'{b}-1c')
        return self.text.index(a+' linestart'), self.text.index(b+' lineend')

    def line_prefix(self, prefix):
        a, b = self.line_bounds()
        lines = self.text.get(a, b).split('\n')
        self.replace(a, b, '\n'.join(prefix + line for line in lines))
        return 'break'

    def heading(self, level):
        a, b = self.line_bounds()
        lines = self.text.get(a, b).split('\n')
        self.replace(a, b, '\n'.join('#' * level + ' ' + re.sub(r'^#{1,6}\s+', '', line) for line in lines))

    def numbered(self):
        a, b = self.line_bounds()
        self.replace(a, b, '\n'.join(f'{i}. {line}' for i, line in enumerate(self.text.get(a, b).split('\n'), 1)))

    def indent(self, out=False):
        a, b = self.line_bounds()
        lines = self.text.get(a, b).split('\n')
        value = '\n'.join(re.sub(r'^( {1,4}|\t)', '', line) if out else '    ' + line for line in lines)
        self.replace(a, b, value)
        # Keep multiline selection for subsequent indent/outdent operations.
        self.text.tag_add('sel', a, f'{a}+{len(value)}c')
        return 'break'

    def enter(self, event=None):
        if self.read_only:
            return 'break'
        a, b = self.bounds()
        if a != b:
            return None  # Tk handles replacement of a selection, including pasted text
        at = self.text.index('insert')
        before = self.text.get(at+' linestart', at)
        match = LIST.match(before)
        if match:
            indent, bullet, checkbox, content = match.groups()
            tail = self.text.get(at, at+' lineend')
            if not content.strip() and not tail.strip():
                self.replace(at+' linestart', at+' lineend', '')
            else:
                if bullet[0].isdigit():
                    bullet = str(int(bullet[:-1]) + 1) + bullet[-1]
                self.replace(at, at, '\n'+indent+bullet+' '+('[ ] ' if checkbox else ''))
            return 'break'
        indent = re.match(r'^\s*', before).group()
        if indent:
            self.replace(at, at, '\n' + indent)
            return 'break'
        return None

    def undo(self):
        if not self.read_only:
            try:
                self.text.edit_undo()
            except tk.TclError:
                pass
            self.on_change()
            self.text.focus_set()
        return 'break'

    def redo(self):
        if not self.read_only:
            try:
                self.text.edit_redo()
            except tk.TclError:
                pass
            self.on_change()
            self.text.focus_set()
        return 'break'

    def link(self):
        if self.read_only:
            return
        url = simpledialog.askstring('Link Markdown', 'Adresă (se inserează ca text, fără accesare automată):', parent=self)
        if url:
            self.wrap('[', '](' + url.replace('\n', '').replace(')', '%29') + ')')

    def template(self):
        if not self.get().strip() and not self.read_only:
            self.replace('1.0', 'end-1c', STRUCTURED)



class ExpandedDescription(tk.Toplevel):
    """Modal peer: cancel rolls back only this editing session; save uses Workspace."""
    def __init__(self, details):
        super().__init__(details)
        self.details = details
        self.before, self.was_dirty = details.editor.get(), details.is_dirty()
        self.title('Descriere — ' + details.vars['title'].get())
        self.geometry('1050x760')
        self.minsize(700, 500)
        self.transient(details.winfo_toplevel())
        self.editor = MarkdownEditor(self, source=details.desc, on_change=details._desc_changed, on_save=self.save)
        self.editor.pack(fill='both', expand=True)
        ttk.Label(self, text='Salvează: scrie descrierea și detaliile taskului. Anulează: revine la textul de la deschidere.', style='Muted.TLabel', wraplength=800).pack(fill='x', padx=12)
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill='x')
        ttk.Button(bar, text='Salvează (Ctrl+S)', command=self.save).pack(side='right')
        ttk.Button(bar, text='Anulează', command=self.cancel).pack(side='right', padx=8)
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda e: self.cancel())
        self.bind('<Control-s>', lambda e: self.save())
        self.grab_set()
        self.editor.text.focus_set()

    def save(self):
        if self.details.save():
            self.close()
        return 'break'

    def cancel(self):
        self.details.editor.replace('1.0', 'end-1c', self.before)
        # Drain the shared modified flag before restoring the prior dirty state.
        self.details.desc.edit_modified(False)
        self.details.desc.edit_reset()
        self.details._dirty = self.was_dirty
        self.details._update_state()
        self.close()
        return 'break'

    def close(self):
        self.grab_release()
        self.details.expanded = None
        self.destroy()
        self.details.desc.focus_set()
