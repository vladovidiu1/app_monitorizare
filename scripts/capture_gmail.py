"""Real Tk Gmail scenarios on temporary data. SMTP/vault are always fake."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language',choices=['ro','en','de','fr','es'],default='ro')
    parser.add_argument('--scale',type=float,default=1)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report={'language':args.language,'scale_simulated':args.scale,'platform':sys.platform,
            'smtp_real':False,'credential_manager_real':False,'windows_dpi_verified':False,'checks':[],'captures':[]}
    with tempfile.TemporaryDirectory(prefix='focusdesk-gmail-ui-') as temporary:
        base=Path(temporary);os.environ['APPDATA']=str(base/'profile')
        profile=base/'profile/FocusDesk/app.json';profile.parent.mkdir(parents=True)
        profile.write_text(json.dumps({'language':args.language}))
        from focusdesk.i18n import tr,language,_missing
        from focusdesk.domain.models import Kind
        from focusdesk.services.gmail import GmailService
        from focusdesk.integrations.gmail import GmailTransport
        from focusdesk.ui.app import FocusDeskApp
        from focusdesk.ui.mail_ui import MailDialog
        from focusdesk.ui.gmail_ui import EmailSettingsDialog
        from focusdesk.ui.common import apply_theme
        from focusdesk.ui.design import px
        import focusdesk.ui.mail_ui as mail_ui
        from focusdesk.services.user_guide import GuideLibrary
        class Vault:
            available=True
            def __init__(self):self.values={}
            def get(self,key):return self.values.get(key)
            def set(self,key,address,password):self.values[key]=password
            def delete(self,key):self.values.pop(key,None)
        class Smtp:
            def __init__(self):self.sent=[];self.logins=0;self.refused={'ion@example.test':(550,b'fake refusal')};self.threads=[]
            def factory(self,*args,**kwargs):self.threads.append(threading.current_thread().name);return self
            def login(self,*args):self.logins+=1
            def quit(self):pass
            def send_message(self,message,**kwargs):self.sent.append(kwargs);return self.refused
        app=FocusDeskApp();errors=[];smtp=Smtp()
        app.root.report_callback_exception=lambda cls,value,tb:errors.append(str(value))
        app.root.tk.call('tk','scaling',args.scale*96/72);apply_theme(app.root)
        app.gmail=GmailService(app.config,app.bridge,secret_store=Vault(),transport=GmailTransport(smtp_ssl=smtp.factory))
        mail_ui.confirm=lambda *args:True
        mail_ui.show_error=lambda *args:errors.append(str(args))
        mail_ui.show_info=lambda *args:None
        def pump(condition=None):
            limit=time.monotonic()+(5 if condition else .1)
            while time.monotonic()<limit:
                app.root.update();time.sleep(.01)
                if condition and condition():return True
            return condition is None or condition()
        def check(name,value):assert value,name;report['checks'].append(name)
        def visible(widget,owner):
            x=widget.winfo_rootx()-owner.winfo_rootx();y=widget.winfo_rooty()-owner.winfo_rooty()
            return widget.winfo_viewable() and x>=0 and y>=0 and x+widget.winfo_width()<=owner.winfo_width() and y+widget.winfo_height()<=owner.winfo_height()
        def shot(name,window):
            if args.output:
                from PIL import ImageGrab
                args.output.mkdir(parents=True,exist_ok=True);window.lift();pump()
                x,y=window.winfo_rootx(),window.winfo_rooty()
                ImageGrab.grab(bbox=(x,y,x+window.winfo_width(),y+window.winfo_height())).save(args.output/(name+'.png'))
                report['captures'].append(name+'.png')
        def snapshot():return {str(p.relative_to(app.ws.root)):p.read_bytes() for p in app.ws.root.rglob('*') if p.is_file() and not p.name.endswith('.lock')}
        dialog=settings=None
        try:
            check('selected language',language()==args.language)
            check('Outlook default',app.config.mail.provider=='outlook')
            check('temporary workspace',app.open_workspace(base/'workspace',create=True))
            task=app.ws.create_node(Kind.TASK,'User task îäéñ',description='Personal text îäéñ\n    indent')
            app.refresh_all();app.select_node(task.id,reveal=True);pump()
            settings=EmailSettingsDialog(app.root,app);pump()
            settings.geometry(f'{px(settings,600)}x{px(settings,360)}+10+10');pump()
            panel=settings.panel;panel.provider_box.current(1);panel.address.set('sender@workspace.example')
            panel.password.set('fake-only-no-real-password');panel.remember.set(True)
            panel.password_entry.focus_force();pump()
            check('password masked',bool(panel.password_entry.cget('show')))
            check('keyboard focus scrolls settings',visible(panel.password_entry,settings))
            check('settings close action at minimum',visible(settings.ok_btn,settings))
            check('settings close label fits',settings.ok_btn.winfo_height()>=settings.ok_btn.winfo_reqheight())
            for index,widget in enumerate(panel.controls[:3]):check('settings action '+str(index),visible(widget,settings))
            before=profile.read_bytes();panel.test();check('async connection test',panel.pending)
            check('connection test completes',pump(lambda:not panel.pending))
            check('connection test sends nothing',smtp.logins==1 and not smtp.sent)
            check('connection test does not save',profile.read_bytes()==before)
            before=snapshot();check('save profile',panel.save())
            check('profile save preserves workspace',snapshot()==before)
            check('secret excluded from JSON','fake-only-no-real-password' not in profile.read_text())
            shot('gmail-settings-minimum',settings);settings.destroy();settings=None
            dialog=MailDialog(app.root,app,task);pump()
            dialog.geometry(f'{px(dialog,680)}x{px(dialog,540)}+10+10');pump()
            dialog.to_var.set('ana@example.test');dialog.cc_var.set('ion@example.test')
            edited='User edited îäéñ\n    keep\n'*20
            dialog.text.delete('1.0','end');dialog.text.insert('1.0',edited)
            file=base/'Document șț Äéñ.txt';file.write_text('Local document îäéñ')
            dialog._select_attachments([file]);before=dialog.collect()
            for index in (0,1):dialog.provider_box.current(index);dialog._provider_changed();pump()
            check('provider switch preserves draft',dialog.collect()==before)
            check('Gmail account visible','sender@workspace.example' in dialog.provider_box.get())
            check('no Outlook draft for Gmail',not dialog.draft_btn.winfo_manager())
            check('local eml action visible',visible(dialog.eml_btn,dialog))
            check('send action at minimum',visible(dialog.ok_btn,dialog))
            shot('gmail-compose-minimum',dialog)
            dialog._on_ok();dialog._on_ok();dialog._open_draft()
            check('partial result arrives',pump(lambda:dialog.partial_result is not None))
            check('only one message despite repeated click',len(smtp.sent)==1)
            check('partial result locks send',dialog.uncertain and str(dialog.ok_btn.cget('state'))=='disabled')
            check('accepted and refused addresses visible',all(a in dialog.message.cget('text') for a in ('ana@example.test','ion@example.test')))
            check('explicit refused-only action visible',visible(dialog.refused_btn,dialog))
            shot('gmail-partial-result',dialog)
            dialog._retry_refused();check('only refused recipients retained',not dialog.to_var.get() and dialog.cc_var.get()=='ion@example.test')
            check('preparing retry does not send',len(smtp.sent)==1)
            smtp.refused={};dialog._on_ok();check('explicit retry completes',pump(lambda:not dialog.winfo_exists()))
            check('accepted recipients not repeated',smtp.sent[-1]['to_addrs']==['ion@example.test'])
            check('SMTP runs off Tk',all(n.startswith('focusdesk_') for n in smtp.threads))
            check('task description unchanged',app.ws.get_description(task.id)=='Personal text îäéñ\n    indent')
            check('Gmail guide available','gmail-configurare' in GuideLibrary().chapters['email'].anchors)
            check('no missing keys',not _missing);check('no Tk errors',not errors)
        finally:
            for window in (dialog,settings):
                if window is not None and window.winfo_exists():window.destroy()
            app.inspector.revert();pump(lambda:not app._pending_workspace_jobs());app.on_close()
    if args.output:(args.output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'language':args.language,'scale':args.scale,'checks':len(report['checks']),'captures':len(report['captures'])}))


if __name__=='__main__':main()
