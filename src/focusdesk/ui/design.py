"""FocusDesk Light: tokens, styles and local MIT icons. No I/O over the network."""
from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
import ttkbootstrap as tb
from ttkbootstrap.style import ThemeDefinition
from ..config import resource_path


@dataclass(frozen=True)
class Palette:
    canvas: str = '#F3F5F9'
    surface: str = '#FFFFFF'
    sidebar: str = '#F8F9FC'
    text: str = '#202838'
    muted: str = '#596579'
    border: str = '#DCE1EB'
    accent: str = '#4F46B8'
    hover: str = '#433A9E'
    selected: str = '#E8E6FA'
    success: str = '#286547'
    warning: str = '#8A5A16'
    danger: str = '#A33342'


C = Palette()
FONT = 'Segoe UI'
BASE = 10
SPACE = (4, 8, 12, 16, 24, 32)
THEME = 'focusdesk-light'
MIN_WINDOW = (1100, 700)
ROW_HEIGHT = 34


def scale(widget):
    return float(widget.tk.call('tk', 'scaling')) / (96 / 72)


def px(widget, value):
    return max(1, round(value * scale(widget)))


def install(root):
    style = tb.Style()
    if THEME not in style.theme_names():
        style.register_theme(ThemeDefinition(THEME, dict(primary=C.accent, secondary=C.muted,
            success=C.success, info=C.accent, warning=C.warning, danger=C.danger, light=C.sidebar,
            dark=C.text, bg=C.surface, fg=C.text, selectbg=C.selected, selectfg=C.text,
            border=C.border, inputfg=C.text, inputbg=C.surface, active=C.selected), mode='light'))
    style.theme_use(THEME)
    families = set(tkfont.families(root))
    family = FONT if FONT in families else 'DejaVu Sans' if 'DejaVu Sans' in families else tkfont.nametofont('TkDefaultFont',root).actual('family')
    for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont','TkCaptionFont','TkTooltipFont','TkIconFont','TkSmallCaptionFont'):
        tkfont.nametofont(name, root).configure(family=family, size=BASE)
    root.configure(background=C.canvas)
    for widget in ('Text','Listbox'):
        for key, value in dict(background=C.surface, foreground=C.text, selectBackground=C.accent,
                selectForeground=C.surface, highlightBackground=C.border, highlightColor=C.accent,
                highlightThickness=1, borderWidth=0, relief='flat', font=(family,BASE)).items():
            root.option_add(f'*{widget}.{key}', value)
    root.option_add('*Text.insertBackground', C.text)
    root.option_add('*Text.padX', 10)
    root.option_add('*Text.padY', 8)
    root.option_add('*Canvas.background', C.surface)
    root.option_add('*Menu.background', C.surface)
    root.option_add('*Menu.foreground', C.text)
    root.option_add('*Menu.activeBackground', C.selected)
    root.option_add('*Menu.activeForeground', C.text)
    root._focusdesk_family=family
    style.configure('.', font=(family,BASE))
    style.configure('TFrame', background=C.surface)
    for name, color in (('Page',C.canvas),('Surface',C.surface),('Sidebar',C.sidebar),('Card',C.surface)):
        style.configure(name+'.TFrame', background=color)
    style.configure('Card.TFrame',borderwidth=1,relief='solid',bordercolor=C.border)
    style.configure('TLabel', background=C.surface, foreground=C.text)
    for name, size, weight, color in (('Title',20,'bold',C.text),('Brand',14,'bold',C.accent),
            ('Section',11,'bold',C.text),('Muted',9,'normal',C.muted),('Crumb',9,'normal',C.muted),
            ('Metric',18,'bold',C.text),('Eyebrow',9,'bold',C.muted)):
        style.configure(name+'.TLabel', font=(family,size,weight), foreground=color)
    style.configure('Page.Title.TLabel', background=C.canvas, font=(family,20,'bold'))
    style.configure('Page.Muted.TLabel', background=C.canvas, foreground=C.muted)
    style.configure('Sidebar.TLabel', background=C.sidebar, foreground=C.muted, font=(family,9,'bold'))
    style.configure('Link.TLabel', foreground=C.accent, font=(family,BASE,'underline'))
    style.configure('TButton', padding=(px(root,10),px(root,6)), background=C.surface,
        foreground=C.text, bordercolor=C.border, focuscolor=C.accent, relief='flat')
    style.map('TButton', background=[('disabled',C.canvas),('pressed',C.selected),('active',C.sidebar)],
        foreground=[('disabled','#737D8E')], bordercolor=[('focus',C.accent),('active','#B8B5DC')])
    # Native ttk layouts preserve keyboard behavior and visible focus.
    for name, bg, fg in (('Primary',C.accent,C.surface),('Secondary',C.surface,C.text),
            ('Quiet',C.surface,C.accent),('Danger',C.surface,C.danger)):
        style.configure(name+'.TButton', padding=(12,7), background=bg, foreground=fg,
            bordercolor=C.border if name=='Secondary' else bg, focuscolor=C.surface if name=='Primary' else C.accent)
        style.map(name+'.TButton', background=[('disabled',C.canvas),('pressed',C.hover if name=='Primary' else C.selected),
            ('active',C.hover if name=='Primary' else C.sidebar)], foreground=[('disabled','#737D8E')],
            bordercolor=[('focus',C.accent)])
    style.configure('primary.TButton',focuscolor=C.surface)
    style.configure('TMenubutton', padding=(12,7))
    style.configure('TEntry', padding=(8,6))
    style.configure('TCombobox', padding=(7,5))
    style.configure('TCheckbutton', padding=(0,4))
    style.configure('TNotebook', background=C.surface, borderwidth=0, tabmargins=(0,4,0,0))
    style.configure('TNotebook.Tab', padding=(12,8), font=(family,9), background=C.sidebar)
    style.map('TNotebook.Tab', background=[('selected',C.surface),('active',C.selected)],
        foreground=[('selected',C.accent),('disabled','#737D8E')])
    style.configure('Inspector.TNotebook.Tab', padding=(5,8), font=(family,9))
    style.configure('Treeview', rowheight=px(root,ROW_HEIGHT), font=(family,BASE), borderwidth=0,
        background=C.surface, fieldbackground=C.surface, foreground=C.text)
    style.configure('Treeview.Heading', font=(family,9,'bold'), background=C.sidebar,
        foreground=C.muted, padding=(8,9), relief='flat')
    style.map('Treeview', background=[('selected',C.selected)], foreground=[('selected',C.text)])
    style.map('Treeview.Heading', background=[('active',C.selected)])
    style.configure('Dense.Treeview', rowheight=px(root,26))
    style.configure('Nav.Treeview', rowheight=px(root,38), background=C.sidebar, fieldbackground=C.sidebar)
    style.configure('TPanedwindow', background=C.canvas, sashwidth=px(root,8))
    if not getattr(root,'_focusdesk_bindings',False):
        root._focusdesk_bindings=True
        root.bind_class('Text','<Map>',_text_surface,add='+')
        root.bind_class('Listbox','<Map>',_text_surface,add='+')
        root.bind_class('TButton','<Map>',_accessible_button,add='+')
        root.bind_class('TFrame','<Map>',_action_surface,add='+')
        root.bind_class('Toplevel','<Map>',_scale_dialog,add='+')
    return style


def icon(widget, name, size=20):
    """Keep images alive per Tcl interpreter; no shared Tk objects across roots."""
    root = widget._root()
    cache = getattr(root, '_focusdesk_icons', None)
    if cache is None:
        root._focusdesk_icons = cache = {}
    target = size * scale(widget)
    nearest = min((16,20,24,32,40,48), key=lambda x:abs(x-target))
    key=(name,nearest)
    if key not in cache:
        cache[key]=tk.PhotoImage(master=widget, file=str(resource_path(f'icons/{name}-{nearest}.png')))
    return cache[key]


def button(parent, text, command, *, kind='Secondary', glyph=None, tooltip=None, **kw):
    result=ttk.Button(parent, text=text, command=command, style=kind+'.TButton', **kw)
    if glyph:
        result.configure(image=icon(parent,glyph+'-on-accent' if kind=='Primary' else glyph), compound='left')
    if tooltip or not text:
        from .common import Tooltip
        Tooltip(result, tooltip or glyph)
    return result


def _text_surface(event):
    widget=event.widget
    widget.configure(borderwidth=0,relief='flat',highlightthickness=1,
        highlightbackground=C.border,highlightcolor=C.accent,background=C.surface,foreground=C.text,
        selectbackground=C.accent,selectforeground=C.surface)


def _accessible_button(event):
    widget=event.widget
    if getattr(widget,'_focusdesk_accessible',False):
        return
    text=str(widget.cget('text'))
    if text.startswith(('Șterge','Golește coșul')):
        widget.configure(style='Danger.TButton')
    labels={'…':('search','Alege sau caută'), '✕':('clear','Elimină selecția'),
        '▲':('up','Mută mai sus'), '▼':('down','Mută mai jos'),
        '◀':('left','Înapoi / scoate un nivel'), '▶':('right','Înainte / creează un subnivel')}
    if text.endswith('…') and text not in labels:
        widget.configure(text=text[:-1])
    if text in labels:
        name,tip=labels[text]
        widget.configure(image=icon(widget,name,16),compound='left',text='',width=2)
        from .common import Tooltip
        if not getattr(widget,"_focusdesk_tooltip",None):
            Tooltip(widget,tip)
    widget._focusdesk_accessible=True


def wrap_actions(frame):
    """Wrap native action buttons onto rows; preserve their commands and focus order."""
    if getattr(frame,'_focusdesk_wrap',False):
        return
    frame._focusdesk_wrap=True
    if frame.winfo_manager()=='pack':
        frame.pack_configure(fill='x')
    elif frame.winfo_manager()=='grid':
        frame.grid_configure(sticky='ew')
    def arrange(_event=None):
        if not frame.winfo_exists():
            return
        width=max(80,frame.winfo_width())
        widgets=frame.winfo_children()
        signature=(width,tuple((str(w),w.winfo_reqwidth()) for w in widgets))
        if getattr(frame,'_focusdesk_signature',None)==signature:
            return
        frame._focusdesk_signature=signature
        for w in widgets:
            if w.winfo_manager()=='pack':
                w.pack_forget()
        row=column=used=0
        for w in widgets:
            need=w.winfo_reqwidth()+8
            if used and used+need>width:
                row+=1;column=used=0
            if w.winfo_manager()=='pack':
                w.pack_forget()
            w.grid(row=row,column=column,sticky='w',padx=(0,6),pady=3)
            column+=1;used+=need
    frame.bind('<Configure>',arrange,add='+')
    arrange()


def _action_surface(event):
    frame=event.widget
    children=frame.winfo_children()
    if frame is getattr(frame.master,'buttons',None):
        return
    if len(children)>1 and all(w.winfo_class()=='TButton' and w.winfo_manager()=='pack' for w in children):
        wrap_actions(frame)


def _scale_dialog(event):
    window=event.widget
    if window is not window.winfo_toplevel() or getattr(window,'_focusdesk_sized',False):
        return
    window._focusdesk_sized=True
    factor=scale(window)
    if factor>1.1 and not window.overrideredirect():
        import re
        match=re.match(r'(\d+)x(\d+)(.*)',window.geometry())
        if match:
            w,h,position=match.groups()
            window.geometry(f'{round(int(w)*factor)}x{round(int(h)*factor)}{position}')
