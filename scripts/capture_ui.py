"""Capturi reale Tk, workspace demonstrativ temporar. Necesită display (Windows sau Xvfb)."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    from PIL import ImageGrab
    from focusdesk.services.demo import create_demo_workspace
    from focusdesk.ui.app import FocusDeskApp
    from focusdesk.ui.mail_ui import MailDialog
    from focusdesk.ui.settings_dialog import SettingsDialog
    from focusdesk.ui.dashboard import DashboardWindow
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/ui'))
    parser.add_argument('--scale',type=float,default=1.0)
    parser.add_argument('--size',default=None)
    args=parser.parse_args()
    args.size=args.size or f"{round(1440*args.scale)}x{round(900*args.scale)}"
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='focusdesk-ui-') as tmp:
        os.environ['APPDATA']=str(Path(tmp)/'config')
        from focusdesk.config import AppConfig
        config=AppConfig(theme='dark');config.save() # verifies legacy migration
        create_demo_workspace(Path(tmp)/'demo')
        app=FocusDeskApp();app.root.withdraw()
        errors=[]
        app.root.report_callback_exception=lambda cls,error,tb:errors.append(f"{cls.__name__}: {error}")
        app.root.tk.call('tk','scaling',args.scale*96/72)
        from focusdesk.ui.common import apply_theme
        apply_theme(app.root,'light')
        from focusdesk.ui.design import px, MIN_WINDOW
        app.root.minsize(*(px(app.root,v) for v in MIN_WINDOW))
        assert app.open_workspace(Path(tmp)/'demo')
        app.root.geometry(args.size+'+0+0');app.root.deiconify()
        def pump():
            for _ in range(12):app.root.update();time.sleep(.025)
        def shot(name,widget=None):
            widget=widget or app.root
            pump();widget.lift();pump()
            box=(widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_rootx()+widget.winfo_width(),widget.winfo_rooty()+widget.winfo_height())
            ImageGrab.grab(bbox=box).save(args.output/(name+'.png'))
        try:
            app.show_view('today',select_sidebar=True);shot('01-astazi')
            project=next(n for n in app.ws.nodes.values() if n.title=='Validări XML')
            task=next(n for n in app.ws.nodes.values() if n.title=='Verificare diferențe XML')
            app.select_node(project.id,reveal=True);shot('02-proiect')
            app.select_node(task.id,reveal=True);app.inspector.show_tab('Detalii');shot('03-inspector')
            app.show_view('calendar',select_sidebar=True);shot('04-calendar')
            app.select_node(task.id,reveal=True)
            app.open_assistant();shot('05-asistent',app.assistant_window);app.assistant_window.destroy()
            dialog=SettingsDialog(app.root,app);dialog.geometry('+30+30');shot('06-setari',dialog)
            dialog.nb.select(dialog.ai_page);shot('07-setari-ai',dialog);dialog.destroy()
            dialog=MailDialog(app.root,app,task);dialog.geometry('+30+30');shot('08-email',dialog);dialog.destroy()
            app.show_view('mail_review');shot('09-mailuri')
            window=DashboardWindow(app);window.geometry('+30+30');shot('10-dashboard',window);window.destroy()
            if errors:
                raise RuntimeError('Erori callback Tk: '+ '; '.join(errors))
            report={'scale_simulated':args.scale,'size':args.size,'platform':sys.platform,'theme':app.config.theme,
                'real_tk':True,'windows_dpi_verified':False,'captures':sorted(p.name for p in args.output.glob('*.png'))}
            (args.output/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        finally:app.on_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
