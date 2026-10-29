"""Real Tk guide screenshots, demo workspace only; no tutorial actions are executed by the guide."""
from __future__ import annotations

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
    from focusdesk.domain.models import Kind
    from focusdesk.ui.app import FocusDeskApp
    from focusdesk.ui.common import apply_theme
    from focusdesk.ui.design import MIN_WINDOW, px

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/guide'))
    parser.add_argument('--scale',type=float,default=1.0)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report=dict(platform=sys.platform,scale_simulated=args.scale,windows_dpi_verified=False,
                native_windows_dialogs_verified=False,captures=[],checks=[])
    with tempfile.TemporaryDirectory(prefix='focusdesk-guide-demo-') as tmp:
        base=Path(tmp);os.environ['APPDATA']=str(base/'config')
        app=FocusDeskApp()
        app.root.tk.call('tk','scaling',args.scale*96/72);apply_theme(app.root)
        app.root.minsize(*(px(app.root,v) for v in MIN_WINDOW))
        app.root.geometry(f'{px(app.root,1100)}x{px(app.root,700)}+0+0')
        errors=[];app.root.report_callback_exception=lambda cls,error,tb:errors.append(f'{cls.__name__}: {error}')
        assert app.open_workspace(base/'data',create=True)
        project=app.ws.create_node(Kind.PROJECT,'Automatizare raport SAP')
        task=app.ws.create_node(Kind.TASK,'Verifică extragerea raportului',project.id,description='Scop\nVerificarea regulilor.\n\nPasul 1\n    Compară documentul exemplu.')
        app.refresh_all();app.select_node(task.id,reveal=True)
        def pump():
            for _ in range(6):app.root.update();time.sleep(.02)
        def rect(widget):return (widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_width(),widget.winfo_height())
        def visible(name,widget,window):
            pump();x,y,w,h=rect(widget);rx,ry,rw,rh=rect(window)
            ok=widget.winfo_viewable() and w>1 and h>1 and rx<=x and ry<=y and x+w<=rx+rw and y+h<=ry+rh
            report['checks'].append(dict(name=name,ok=bool(ok)));assert ok,name
        def shot(name,window):
            pump();window.lift();pump();x,y,w,h=rect(window)
            ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(args.output/(name+'.png'))
            report['captures'].append(name+'.png')
        try:
            pump()
            visible('antet-ghid',app.guide_btn,app.root)
            visible('antet-cautare',app.search_entry,app.root)
            visible('antet-nou',app.new_btn,app.root)
            assert rect(app.guide_btn)[0]+rect(app.guide_btn)[2] <= rect(app.search_entry)[0]
            shot('ghid-acces-antet',app.root)
            window=app.show_guide('descriere');pump()
            window.geometry(f'{px(window,760)}x{px(window,500)}+20+20');pump()
            for name in ('search_entry','back_btn','forward_btn','toc','article','link_combo','link_btn','close_btn'):
                visible('minim-'+name,getattr(window,name),window)
            shot('ghid-descriere-minim',window)
            window.query.set('intalniri');window.search();pump()
            hit=window.toc.get_children()[0];window.toc.selection_set(hit);window.toc.focus(hit);pump()
            assert window.preview.cget('text')
            shot('ghid-cautare',window)
            window.query.set('');window.search();window.close();pump()
            # Demonstrate modal help hosting with an isolated expanded-editor draft.
            details=app.inspector.tab_by_title('Detalii');details.expand_description();pump()
            editor=details.expanded;editor.editor.text.focus_force();pump()
            before=details.editor.get();grab=app.root.grab_current()
            modal_help=app.show_guide(contextual=True);pump()
            assert modal_help.master is editor and app.root.grab_current() is grab
            modal_help.geometry(f'{px(modal_help,760)}x{px(modal_help,500)}+20+20')
            shot('ghid-din-editor-modal',modal_help)
            modal_help.close();editor.cancel();pump()
            assert details.editor.get()==before and not errors,errors
        finally:
            app.inspector.revert()
            deadline=time.monotonic()+5
            while app._pending_workspace_jobs() and time.monotonic()<deadline:app.root.update();time.sleep(.01)
            app.on_close()
    (args.output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
