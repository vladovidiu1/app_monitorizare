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
            dialog=SettingsDialog(app.root,app);dialog.geometry('+30+30');shot('06-setari',dialog);dialog.destroy()
            dialog=MailDialog(app.root,app,task);dialog.geometry('+30+30');shot('08-email',dialog);dialog.destroy()
            window=DashboardWindow(app);window.geometry('+30+30');shot('10-dashboard',window);window.destroy()
            from focusdesk.domain.models import Kind, Status
            from focusdesk.domain.labels import STATUS_LABELS
            demo_project = app.ws.create_node(Kind.PROJECT, 'Exemple de status')
            sample = '# Obiectiv\n\nDocumentare **clară** și *ușor de revizuit*.\n\n## Pași / cerințe\n\n- Primul pas\n- [ ] Căsuță Markdown (documentare)\n\n1. Verifică datele\n2. Salvează rezultatul\n\n[Documentație](https://example.com)\n\n```python\nprint("Exemplu de cod; nu se execută")\n```'
            statuses = (Status.TODO, Status.IN_PROGRESS, Status.WAITING, Status.TESTING, Status.DONE, Status.CANCELLED)
            nodes = [app.ws.create_node(Kind.TASK, STATUS_LABELS[state], demo_project.id, status=state, description=sample) for state in statuses]
            app.refresh_all()
            app.show_node_scope(demo_project.id)
            app.tasklist.closed_var.set(True);app.tasklist.refresh()
            app.select_node(nodes[-2].id)
            pump()
            assert app.current_scope == demo_project.id and app.selected_id == nodes[-2].id
            shot('11-statusuri')
            tab = app.inspector.tab_by_title('Detalii')
            tab.expand_description()
            window = tab.expanded
            window.geometry('1050x760+30+30')
            window.editor.notebook.select(1)
            window.editor.render()
            shot('12-descriere-previzualizare',window)
            window.cancel()
            if errors:
                raise RuntimeError('Erori callback Tk: '+ '; '.join(errors))
            report={'scale_simulated':args.scale,'size':args.size,'platform':sys.platform,'theme':app.config.theme,
                'real_tk':True,'windows_dpi_verified':False,'captures':sorted(p.name for p in args.output.glob('*.png'))}
            (args.output/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        finally:app.on_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
