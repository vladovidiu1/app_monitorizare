"""Nonmodal, single visible manual; modal hosts keep their existing grab unchanged."""
from __future__ import annotations

from ..i18n import tr

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from ..services.user_guide import GuideError, GuideHistory, GuideLibrary
from .common import Tooltip
from .design import C, px

TOPICS = {
    'MarkdownEditor':'descriere', 'ExpandedDescription':'descriere', 'DescriptionGuide':'descriere',
    'DescriptionMergeDialog':'descriere', 'DetailsTab':'descriere', 'SubtasksTab':'organizare',
    'FilesTab':'fisiere', 'FileExplorer':'fisiere', 'ReferenceDialog':'fisiere',
    'JournalTab':'sesiuni#jurnalul-taskului', 'VersionsTab':'versiuni', 'PlanTab':'calendar',
    'MailDialog':'email', 'DescriptionSourceDialog':'email', 'TaskFilePicker':'email#atasamente',
    'EmailSettingsDialog':'email#gmail-configurare', 'EmailSettingsPanel':'email#gmail-configurare',
    'StopSessionDialog':'sesiuni', 'CorrectTimeDialog':'sesiuni',
    'ManualSessionDialog':'calendar', 'PlannerDialog':'calendar', 'RecurrenceDialog':'calendar',
    'FollowupDialog':'cerinte', 'ReopenReasonDialog':'cerinte',
    'CreateTemplateDialog':'sabloane', 'TemplateEditor':'sabloane', 'TemplateManager':'sabloane',
    'MeetingPage':'intalniri', 'ManualMeetingDialog':'intalniri', 'CalendarSourceDialog':'intalniri',
    'ActionDialog':'intalniri', 'MeetingNodeDialog':'intalniri',
    'SettingsDialog':'setari', 'TrashDialog':'siguranta', 'IssuesDialog':'probleme',
    'DashboardWindow':'activitate',
    'NewNodeDialog':'organizare', 'MoveDialog':'organizare', 'ColleaguePickerDialog':'setari#colegi-si-solicitant',
    'OutlookDiagnosticDialog':'setari#outlook-classic-si-lucru-offline',
}


def _native_host(root, path):
    """Wrap an existing Tcl dialog without creating/destroying it or changing its grab.

    Tcl-native dialogs are not always registered in tkinter's Python children map.
    Register only window wrappers, so normal nametowidget/focus/style handling works.
    """
    parent = root
    for name in path.lstrip('.').split('.'):
        if name in parent.children:
            parent = parent.children[name]
            continue
        proxy = tk.Widget.__new__(tk.Widget)
        proxy.master, proxy.tk, proxy._name = parent, root.tk, name
        proxy._w = (parent._w if parent._w != '.' else '') + '.' + name
        proxy.children, proxy._tclCommands = {}, []
        proxy._focusdesk_sized = True  # Do not resize a native dialog when wrapping it.
        parent.children[name] = proxy
        def destroyed(event, proxy=proxy, owner=parent, name=name):
            if str(event.widget) == proxy._w:
                owner.children.pop(name, None)
                def forget(widget):
                    for child in list(widget.children.values()):forget(child)
                    widget.children.clear()
                    tk.Misc.destroy(widget)  # Tcl already destroyed the native window/subtree.
                forget(proxy)
        proxy.bind('<Destroy>', destroyed, add='+')
        parent = proxy
    return parent


class GuideController:
    def __init__(self, app):
        self.app = app
        self.library = None
        self.history = GuideHistory()
        self.window = None
        self.query = ''

    def context_topic(self):
        try: widget = self.app.root.focus_get()
        except (KeyError, tk.TclError): widget = None
        while widget is not None:
            if self.window is not None and widget is self.window:
                return self.history.current.chapter_id
            topic = TOPICS.get(type(widget).__name__)
            if topic: return topic
            widget = getattr(widget, 'master', None)
        # A modal can have focus on its border rather than in an editor.
        try:
            grab = self.app.root.grab_current()
            if grab is not None and type(grab).__name__ in TOPICS: return TOPICS[type(grab).__name__]
        except (tk.TclError, KeyError): pass
        if self.app.ws is None: return 'primii-pasi'
        view = self.app.current_view
        if view == 'calendar':
            hub = self.app.calendar_page
            return 'intalniri' if hub.nb.select() == str(hub.meetings) else 'calendar'
        if view == 'task_space':
            space = self.app.task_space
            selected = space.nb.select()
            if str(space.secondary) in space.body.panes():
                for name, frame in space.scrolls.items():
                    if str(frame) == selected:
                        return {'steps':'organizare', 'files':'fisiere', 'journal':'sesiuni#jurnalul-taskului',
                                'planning':'calendar', 'versions':'versiuni'}[name]
            return 'descriere'
        return {'today':'astazi','activity':'activitate','archive':'siguranta'}.get(view, 'organizare')

    def _host(self):
        root = self.app.root
        path = str(root.tk.call('grab', 'current', str(root)))
        if path and self.window is not None and (path == str(self.window) or path.startswith(str(self.window)+'.')):
            return self.window.master
        if path and root.tk.call('winfo','exists',path):
            try: return root.nametowidget(path)
            except KeyError: return _native_host(root, path)
        return root

    def open(self, chapter=None, *, contextual=False):
        if contextual: chapter = self.context_topic()
        host = self._host()
        try: previous_focus = str(self.app.root.tk.call('focus'))
        except tk.TclError: previous_focus = ''
        error = ''
        if self.library is None:
            try: self.library = GuideLibrary()
            except GuideError as exc: error = str(exc)
        if self.window is not None and (not self.window.winfo_exists() or str(self.window.master) != str(host)):
            if self.window.winfo_exists(): self.window.destroy()
            self.window = None
        if self.window is None:
            self.window = GuideWindow(host, self, error=error)
        window = self.window
        window.previous_focus = previous_focus if not previous_focus.startswith(str(window)) else window.previous_focus
        window.deiconify()
        window.lift()
        if chapter is not None and self.library is not None:
            try:
                topic, _, anchor = chapter.removeprefix('guide:').partition('#')
                self.library.target('guide:'+topic+('#'+anchor if anchor else ''))
                window.navigate(topic, anchor)
            except GuideError as exc: window.status.configure(text=str(exc))
        window.article.focus_set()
        return window

    def reload(self):
        self.library = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
        return self.open()


class GuideWindow(tk.Toplevel):
    def __init__(self, parent, controller, *, error=''):
        super().__init__(parent)
        self.controller, self.library = controller, controller.library
        self.title(tr('ui.user_guide.ghid_de_utilizare_focusdesk'))
        self.transient(str(self.tk.call('winfo','toplevel',str(parent))))
        self.geometry('1060x730')
        self.minsize(px(self,760),px(self,500))
        self._focusdesk_sized = True
        self.geometry(f'{px(self,1060)}x{px(self,730)}')
        self.previous_focus = ''
        self._rendering = False
        self._search_job = None
        self._hits = {}
        self._toc_updating = False
        self._article_id = ''
        self._links = []
        self._link_tags = []
        self._link_commands = []
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Escape>', lambda _e: self.close() or 'break')
        self.bind('<Control-f>', lambda _e: self.focus_search())
        self.bind('<Control-s>', lambda _e: 'break')
        self.bind('<Alt-Left>', lambda _e: self.go(-1) or 'break')
        self.bind('<Alt-Right>', lambda _e: self.go(1) or 'break')
        top = ttk.Frame(self,padding=12)
        top.pack(fill='x')
        top.columnconfigure(1,weight=1)
        ttk.Label(top,text=tr('ui.user_guide.cauta_in_ghid')).grid(row=0,column=0,padx=(0,8))
        self.query = tk.StringVar(value=controller.query)
        self.search_entry = ttk.Entry(top,textvariable=self.query)
        self.search_entry.grid(row=0,column=1,sticky='ew')
        self.clear_btn = ttk.Button(top,text=tr('ui.user_guide.goleste'),command=lambda:self.query.set(''))
        self.clear_btn.grid(row=0,column=2,padx=(8,0))
        nav = ttk.Frame(self,padding=(12,0,12,8)); nav.pack(fill='x')
        self.back_btn = ttk.Button(nav,text=tr('ui.meetings.inapoi'),command=lambda:self.go(-1));self.back_btn.pack(side='left')
        self.forward_btn = ttk.Button(nav,text=tr('ui.user_guide.inainte'),command=lambda:self.go(1));self.forward_btn.pack(side='left',padx=6)
        self.close_btn = ttk.Button(nav,text=tr('ui.user_guide.inchide_ghidul'),command=self.close);self.close_btn.pack(side='right')
        self.status = ttk.Label(self,text=tr('ui.user_guide.ajutor_local_cautare_numai_in_documentatie'),style='Muted.TLabel',padding=(12,5))
        self.status.pack(side='bottom',fill='x')
        self.panes = ttk.PanedWindow(self,orient='horizontal');self.panes.pack(fill='both',expand=True,padx=12,pady=(0,8))
        self.left = ttk.Frame(self.panes);self.panes.add(self.left,weight=0)
        self.count = ttk.Label(self.left,text=tr('ui.user_guide.cuprins'),style='Section.TLabel');self.count.pack(anchor='w',pady=(0,6))
        wrap=ttk.Frame(self.left);wrap.pack(fill='both',expand=True)
        self.toc=ttk.Treeview(wrap,show='tree',selectmode='browse',style='Dense.Treeview')
        self.toc.column('#0',width=px(self,255),minwidth=px(self,160),stretch=True)
        sb=ttk.Scrollbar(wrap,command=self.toc.yview);self.toc.configure(yscrollcommand=sb.set)
        sb.pack(side='right',fill='y');self.toc.pack(side='left',fill='both',expand=True)
        self.preview=ttk.Label(self.left,text='',style='Muted.TLabel',wraplength=240,justify='left')
        self.preview.pack(fill='x',pady=(6,0))
        self.toc.bind('<<TreeviewSelect>>',self._toc_selected)
        self.toc.bind('<Return>',lambda _e:self._activate_toc())
        self.toc.bind('<Double-1>',lambda _e:self._activate_toc())
        self.path_tip=Tooltip(self.toc,tr('ui.user_guide.selecteaza_un_capitol_enter_il_deschide'))
        right=ttk.Frame(self.panes);self.panes.add(right,weight=1)
        links=ttk.Frame(right);links.pack(side='bottom',fill='x',pady=(6,0));links.columnconfigure(1,weight=1)
        ttk.Label(links,text=tr('ui.user_guide.legaturi_in_articol')).grid(row=0,column=0,padx=(0,6))
        self.link_combo=ttk.Combobox(links,state='readonly',width=15)
        self.link_combo.grid(row=0,column=1,sticky='ew')
        self.link_btn=ttk.Button(links,text=tr('ui.user_guide.deschide'),command=self._activate_link)
        self.link_btn.grid(row=0,column=2,padx=(6,0))
        self.link_combo.bind('<Return>',lambda _e:self._activate_link() or 'break')
        article=ttk.Frame(right);article.pack(fill='both',expand=True)
        self.article=tk.Text(article,wrap='word',state='disabled',takefocus=True,width=25,
                             font=(self._root()._focusdesk_family,11),padx=14,pady=10)
        self.article.pack(side='left',fill='both',expand=True)
        self.vbar=ttk.Scrollbar(article,command=self.article.yview);self.vbar.pack(side='right',fill='y')
        self.article.configure(yscrollcommand=self._scrolled)
        family=self._root()._focusdesk_family
        for level,size in ((1,18),(2,14),(3,12)):
            self.article.tag_configure(f'h{level}',font=(family,size,'bold'),spacing1=12,spacing3=7)
        self.article.tag_configure('paragraph',spacing3=10)
        self.article.tag_configure('list',lmargin1=8,lmargin2=25,spacing3=5)
        self.article.tag_configure('note',foreground=C.muted,background=C.sidebar,lmargin1=12,lmargin2=12,spacing3=8)
        self.article.tag_configure('bold',font=(family,11,'bold'))
        fixed=tkfont.nametofont('TkFixedFont',self).actual('family')
        self.article.tag_configure('code',font=(fixed,10),background=C.sidebar,spacing3=8)
        self.article.tag_configure('inline-code',font=(fixed,10),background=C.sidebar)
        self.article.tag_configure('link',foreground=C.accent,underline=True)
        self.bind('<Configure>',self._resized)
        self.bind('<Destroy>',self._destroyed)
        self._query_trace=self.query.trace_add('write',self._query_changed)
        if self.library is None:
            self.search_entry.state(['disabled'])
            self.status.configure(text=tr('ui.user_guide.ghid_indisponibil_aplicatia_si_datele_raman_accesibile'))
            self.article.configure(state='normal');self.article.insert('1.0',error);self.article.configure(state='disabled')
            self.retry_btn=ttk.Button(nav,text=tr('ui.user_guide.reincearca_incarcarea'),command=controller.reload);self.retry_btn.pack(side='left')
        else:
            self.search()
            self.render()
        self.after_idle(lambda:self.panes.sashpos(0,px(self,270)) if self.winfo_exists() else None)

    def _resized(self,event):
        if event.widget is self:
            self.preview.configure(wraplength=max(120,self.left.winfo_width()-12))
            self.status.configure(wraplength=max(250,event.width-28))

    def _scrolled(self,first,last):
        self.vbar.set(first,last)
        if not self._rendering and self.library is not None and self._article_id:
            self.controller.history.current.scroll=float(first)

    def _query_changed(self,*_):
        self.controller.query=self.query.get()
        if self._search_job: self.after_cancel(self._search_job)
        self._search_job=self.after(150,self.search)

    def search(self):
        if self._search_job:self.after_cancel(self._search_job);self._search_job=None
        if self.library is None:return
        query=self.query.get().strip()
        self._toc_updating=True
        self.toc.delete(*self.toc.get_children());self._hits={}
        if query:
            hits=self.library.search(query)
            for hit in hits:
                self._hits[hit.chapter_id]=hit
                self.toc.insert('','end',iid=hit.chapter_id,text=hit.title)
            self.count.configure(text=tr('ui.user_guide.capitole_gasite', count=len(hits), len_hits=len(hits)) if hits else tr('ui.user_guide.niciun_rezultat'))
            self.preview.configure(text=tr('ui.user_guide.selecteaza_un_rezultat_pentru_fragment_enter_il_deschide') if hits else tr('ui.user_guide.nu_exista_rezultate_in_ghid_incearca_alte_cuvinte_cu_sau_fara_diacriti'))
        else:
            for chapter in self.library.chapters.values():self.toc.insert('','end',iid=chapter.id,text=chapter.title)
            self.count.configure(text=tr('ui.user_guide.cuprins'));self.preview.configure(text='')
        current=self.controller.history.current.chapter_id
        if self.toc.exists(current):self.toc.selection_set(current)
        self._toc_updating=False

    def _toc_selected(self,_event=None):
        selected=self.toc.selection()
        if not selected or self._toc_updating:return
        chapter_id=selected[0]
        hit=self._hits.get(chapter_id)
        if hit:
            self.preview.configure(text=hit.fragment)
            self.path_tip.text=hit.title+'\n'+hit.fragment
        elif self.library:
            self.path_tip.text=self.library.chapters[chapter_id].title
            self.navigate(chapter_id)

    def _activate_toc(self):
        selected=self.toc.selection()
        if selected:
            hit=self._hits.get(selected[0])
            self.navigate(selected[0],hit.anchor if hit else '')
        return 'break'

    def navigate(self,chapter_id,anchor=''):
        if self.library is None:return
        self.library.target('guide:'+chapter_id+('#'+anchor if anchor else ''))
        changed=self.controller.history.visit(chapter_id,anchor)
        if anchor and not changed:
            self.controller.history.current.scroll=None
        if changed or anchor or self._article_id != chapter_id:self.render()
        self._history_buttons()

    def go(self,delta):
        if self.library is not None and self.controller.history.move(delta):self.render()

    def _history_buttons(self):
        history=self.controller.history
        self.back_btn.state(['!disabled'] if history.index else ['disabled'])
        self.forward_btn.state(['!disabled'] if history.index+1<len(history.entries) else ['disabled'])

    def _inline(self,text,tags):
        token=re.compile(r'\*\*(.+?)\*\*|`([^`]+)`|(?<!!)\[([^\]]+)\]\(([^)]+)\)')
        offset=0
        for match in token.finditer(text):
            self.article.insert('end',text[offset:match.start()],tags)
            if match[1] is not None:self.article.insert('end',match[1],(*tags,'bold'))
            elif match[2] is not None:self.article.insert('end',match[2],(*tags,'inline-code'))
            else:
                label,url=match[3],match[4]
                try:self.library.target(url,self._article_id)
                except GuideError:self.article.insert('end',label,tags)
                else:
                    tag=f'guide-link-{len(self._links)}'
                    self._links.append((label,url));self._link_tags.append(tag)
                    self.article.insert('end',label,(*tags,'link',tag))
                    self._link_commands.append(self.article.tag_bind(tag,'<Button-1>',lambda _e,url=url:self.open_link(url)))
                    self._link_commands.append(self.article.tag_bind(tag,'<Enter>',lambda _e:self.article.configure(cursor='hand2')))
                    self._link_commands.append(self.article.tag_bind(tag,'<Leave>',lambda _e:self.article.configure(cursor='xterm')))
            offset=match.end()
        self.article.insert('end',text[offset:],tags)

    def render(self):
        location=self.controller.history.current
        chapter=self.library.chapters[location.chapter_id]
        fraction=location.scroll
        self._rendering=True
        self._article_id=chapter.id
        self.article.configure(state='normal')
        for tag in self._link_tags:self.article.tag_delete(tag)
        for command in self._link_commands:self.article.deletecommand(command)
        for mark in self.article.mark_names():
            if mark.startswith('heading:'):self.article.mark_unset(mark)
        self._links=[];self._link_tags=[];self._link_commands=[]
        self.article.delete('1.0','end')
        for block in chapter.blocks:
            if block.anchor:
                self.article.mark_set('heading:'+block.anchor,'end-1c')
                self.article.mark_gravity('heading:'+block.anchor,'left')
            tags=(f'h{block.level}',) if block.kind=='heading' else (block.kind,)
            if block.kind=='code':self.article.insert('end',block.text,tags)
            else:self._inline(block.text,tags)
            self.article.insert('end','\n',tags)  # Tags provide paragraph/heading spacing.
        self.article.configure(state='disabled')
        self.link_combo.configure(values=[label for label,_url in self._links],state='readonly' if self._links else 'disabled')
        self.link_btn.state(['!disabled'] if self._links else ['disabled'])
        if self._links:self.link_combo.current(0)
        else:self.link_combo.set('')
        self.article.update_idletasks()
        # Tk otherwise estimates undisplayed line heights, shifting yview after a
        # chapter with mixed heading/body fonts is re-created. Manuals are small.
        self.article.count('1.0','end','update','ypixels')
        if fraction is not None:self.article.yview_moveto(fraction)
        elif location.anchor:self.article.yview('heading:'+location.anchor)
        else:self.article.yview_moveto(0)
        self.article.update_idletasks()
        self._rendering=False
        location.scroll=self.article.yview()[0]
        self.status.configure(text=tr('ui.user_guide.ghid_local')+chapter.title)
        if self.toc.exists(chapter.id) and self.toc.selection() != (chapter.id,):self.toc.selection_set(chapter.id)
        self._history_buttons()

    def open_link(self,url):
        chapter_id,anchor=self.library.target(url,self._article_id)
        self.navigate(chapter_id,anchor)
        return 'break'

    def _activate_link(self):
        index=self.link_combo.current()
        if 0<=index<len(self._links):self.open_link(self._links[index][1])

    def focus_search(self):
        self.search_entry.focus_set();self.search_entry.selection_range(0,'end')
        return 'break'

    def close(self):
        self.withdraw()
        try:
            if self.previous_focus and self.tk.call('winfo','exists',self.previous_focus):self.tk.call('focus',self.previous_focus)
        except tk.TclError:pass

    def _destroyed(self,event):
        if event.widget is self:
            trace=getattr(self,'_query_trace',None)
            if trace:
                self.query.trace_remove('write',trace);self._query_trace=None
            if self._search_job:self.after_cancel(self._search_job);self._search_job=None
            if self.controller.window is self:self.controller.window=None
