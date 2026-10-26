"""Light theme, real Tk layout, resource packaging and accessibility regressions."""
import json
import tkinter as tk
import pytest
from tkinter import ttk

from test_ai_ui import ui
from test_mail_ui import pump
from focusdesk.config import AppConfig, resource_path
from focusdesk.ui.app import FocusDeskApp
from focusdesk.ui.common import apply_theme, is_dark
from focusdesk.ui.design import C, THEME, icon
from focusdesk.ui.mail_ui import MailDialog
from focusdesk.ui.settings_dialog import SettingsDialog


def test_old_dark_config_starts_light_without_losing_ai_preferences(ws,tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path/'config'))
    config=AppConfig(theme='dark',geometry='1100x700')
    config.ai.threads=3
    config.save()
    try:
        app=FocusDeskApp()
    except tk.TclError as exc:
        pytest.skip(f"Tk display indisponibil: {exc}")
    try:
        assert app.config.theme=='light' and not is_dark(app.root)
        assert ttk.Style().theme_use()==THEME
        assert app.config.ai.threads==3
        # A child owns this Tcl command: global cancellation must preserve its cleanup ledger.
        child=ttk.Frame(app.root)
        child.after(60000,lambda:None)
        app.dark_var.set(True)
        app.toggle_theme()
        assert not app.dark_var.get() and app.config.theme=='light'
        assert 'Temă întunecată' not in str(app.menubar)
    finally:
        app.on_close()
    assert AppConfig.load().theme=='light'


def test_visual_tokens_have_readable_contrast_and_local_icons(ui):
    def luminance(color):
        parts=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in parts]
        return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    def ratio(a,b):
        x,y=sorted((luminance(a),luminance(b)))
        return (y+.05)/(x+.05)
    for text,bg in ((C.text,C.surface),(C.muted,C.surface),(C.text,C.selected),(C.surface,C.accent)):
        assert ratio(text,bg)>=4.5
    assert icon(ui.root,'calendar') is icon(ui.root,'calendar')
    assert resource_path('icons/LICENSE.txt').exists()
    assert resource_path('icons/assistant-24.png').exists()
    assert ui.search_entry.cget('takefocus') != '0'


def test_minimum_layout_keeps_save_filters_and_columns_reachable(ui):
    errors=[]
    ui.root.report_callback_exception=lambda *args:errors.append(args)
    ui.root.deiconify();ui.root.geometry('1100x700')
    ui._apply_sashes()
    ui.root.update()
    ui.inspector.show_tab('Detalii')
    details=ui.inspector.tab_by_title('Detalii')
    details.sf.canvas.yview_moveto(1)
    for _ in range(3):ui.root.update()
    assert details.save_btn.winfo_ismapped()
    assert details.save_btn.winfo_rooty()+details.save_btn.winfo_height()<=ui.inspector.winfo_rooty()+ui.inspector.winfo_height()
    assert ui.tasklist.hbar.winfo_ismapped()
    ui.tasklist.tv.xview_moveto(1)
    ui.root.update()
    assert ui.tasklist.tv.xview()[1]>.99
    assert not errors


def test_late_dialog_text_surface_and_icon_tooltips_are_consistent(ui):
    errors=[]
    ui.root.report_callback_exception=lambda *args:errors.append(args)
    ui.root.deiconify()
    ui.root.update()
    dialog=MailDialog(ui.root,ui,ui.ws.get(ui.selected_id))
    dialog.deiconify()
    for _ in range(3):ui.root.update()
    assert dialog.text.cget('background').upper()==C.surface
    assert int(dialog.text.cget('highlightthickness'))==1
    assert dialog.text.cget('highlightcolor').upper()==C.accent
    assert dialog.to_entry.cget('takefocus')!='0'
    dialog.destroy()
    settings=SettingsDialog(ui.root,ui)
    settings.nb.select(settings.ai_page)
    for _ in range(3):ui.root.update()
    controls=[w for w in settings.ai_page.winfo_children() if isinstance(w,ttk.Frame)]
    assert all(w.winfo_ismapped() for frame in controls for w in frame.winfo_children() if isinstance(w,ttk.Button))
    settings.destroy()
    assert not errors
