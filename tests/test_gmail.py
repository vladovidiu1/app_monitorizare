"""No real accounts, credential writes or network connections in this module."""
from __future__ import annotations
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from pathlib import Path
import smtplib
import socket
import ssl
import threading
import time
from types import SimpleNamespace
import zipfile
import pytest

from focusdesk.config import AppConfig
from focusdesk.domain.mail import MailSettings
from focusdesk.integrations.credentials import WindowsCredentialStore,CredentialUnavailable
from focusdesk.integrations.gmail import (GmailCredentials,GmailResult,GmailTransport,GmailError,
                                          GmailUncertain,mime_message,normalize_password)
from focusdesk.services.gmail import GmailService,save_eml,journal_text
from focusdesk.services.mail import build_draft

SECRET='fake-apppassword-NOT-A-REAL-SECRET'


class FakeVault:
    def __init__(self,available=True):self.available=available;self.values={}
    def check(self):
        if not self.available:raise CredentialUnavailable()
    def get(self,key):self.check();return self.values.get(key)
    def set(self,key,address,password):self.check();self.values[key]=password
    def delete(self,key):self.check();self.values.pop(key,None)


class FakeSMTP:
    def __init__(self,*,failure=None,refused=None,gate=None,fail_quit=False):
        self.calls=[];self.failure=failure;self.refused=refused or {};self.gate=gate;self.fail_quit=fail_quit;self.messages=[]
        self.threads=set();self.login_count=0
    def factory(self,*args,**kw):
        self.threads.add(threading.current_thread().name);self.calls.append(('connect',args,kw))
        if self.failure and self.failure[0]=='connect':raise self.failure[1]
        return self
    def ehlo(self):self.calls.append(('ehlo',))
    def starttls(self,**kw):
        self.calls.append(('starttls',kw))
        if self.failure and self.failure[0]=='tls':raise self.failure[1]
    def login(self,address,password):
        self.login_count+=1;self.calls.append(('login',address))
        assert password==SECRET
        if self.failure and self.failure[0]=='login':raise self.failure[1]
    def send_message(self,message,**kwargs):
        self.calls.append(('send',));self.messages.append((message,kwargs))
        if self.gate:self.gate.wait(3)
        if self.failure and self.failure[0]=='send':raise self.failure[1]
        return self.refused
    def quit(self):
        self.calls.append(('quit',))
        if self.fail_quit:raise TimeoutError(SECRET)
    def close(self):self.calls.append(('close',))


def transport(fake,port=465):return GmailTransport(port=port,smtp_ssl=fake.factory,smtp_starttls=fake.factory,timeout=3)
def credentials():return GmailCredentials('sender@workspace.example',SECRET,'Ștefan Äéñ')
def draft():return build_draft('ana@example.test','ion@example.test','Întrebare — Grüße éñ','  Corp îäéñ\n    indentat\n'+('Lung\n'*1700))


def pump(app,condition,seconds=5):
    limit=time.monotonic()+seconds
    while time.monotonic()<limit:
        app.root.update()
        if condition():return True
        time.sleep(.01)
    return condition()


def test_default_profile_and_secret_fields():
    assert AppConfig().mail.provider=='outlook'
    assert AppConfig.model_validate({}).mail.provider=='outlook'
    assert 'password' not in MailSettings.model_fields
    assert SECRET not in repr(credentials())
    assert normalize_password('abcd efgh  ijkl mnop')=='abcdefghijklmnop'
    assert normalize_password('punctuation-ä!')=='punctuation-ä!'
    with pytest.raises(GmailError):normalize_password('secret\nline')


def test_mime_complete_unicode_body_multiple_attachments_and_eml(tmp_path):
    files=[]
    for name,data in [('Măsurări Äéñ.txt',b'document 1'),('raport.pdf',b'%PDF-test')]:
        path=tmp_path/name;path.write_bytes(data);files.append(path)
    original=replace(draft(),attachments=__import__('focusdesk.services.mail',fromlist=['attachment_selection']).attachment_selection(files))
    message=mime_message(original,credentials().address,credentials().display_name)
    decoded=BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    assert str(decoded['From']).endswith('<sender@workspace.example>')
    assert decoded['Date'] and decoded['Message-ID'] and decoded['Cc']=='ion@example.test'
    assert decoded.get_body(preferencelist=('plain',)).get_content().replace('\r\n','\n')==original.body
    assert [(p.get_filename(),p.get_payload(decode=True)) for p in decoded.iter_attachments()]==[(p.name,p.read_bytes()) for p in files]
    eml=tmp_path/'local.eml';save_eml(eml,original,credentials().address)
    assert len(list(BytesParser(policy=policy.default).parsebytes(eml.read_bytes()).iter_attachments()))==2


@pytest.mark.parametrize('port',[465,587])
def test_tls_and_auth_connection_test_never_sends(port):
    fake=FakeSMTP();assert transport(fake,port).test(credentials()) is True
    assert not fake.messages and fake.login_count==1
    args,options=fake.calls[0][1:]
    assert args==('smtp.gmail.com',port) and options['timeout']==3
    context=options['context'] if port==465 else next(c[1]['context'] for c in fake.calls if c[0]=='starttls')
    assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
    if port==587:assert [c[0] for c in fake.calls]==['connect','ehlo','starttls','ehlo','login','quit']


def test_starttls_failure_never_authenticates_or_falls_back():
    fake=FakeSMTP(failure=('tls',RuntimeError(SECRET)))
    with pytest.raises(GmailError) as error:transport(fake,587).test(credentials())
    assert error.value.kind=='tls' and SECRET not in str(error.value)
    assert fake.login_count==0 and len([c for c in fake.calls if c[0]=='connect'])==1


@pytest.mark.parametrize('error,kind',[
    (socket.gaierror('DNS '+SECRET),'network'),(TimeoutError(SECRET),'timeout'),
    (ssl.SSLError(SECRET),'tls'),(smtplib.SMTPAuthenticationError(535,SECRET.encode()),'auth'),
    (smtplib.SMTPAuthenticationError(534,SECRET.encode()),'auth_policy'),
    (smtplib.SMTPDataError(452,SECRET.encode()),'limit'),(smtplib.SMTPDataError(552,SECRET.encode()),'message'),
    (smtplib.SMTPDataError(550,b'5.4.5 Daily user sending quota exceeded'),'limit'),
    (smtplib.SMTPAuthenticationError(454,b'Too many login attempts'),'limit')])
def test_sanitized_failures_and_no_debug_smtp_logs(error,kind,caplog):
    fake=FakeSMTP(failure=('login',error))
    with pytest.raises(GmailError) as result:transport(fake).test(credentials())
    assert result.value.kind==kind
    assert SECRET not in str(result.value) and SECRET not in caplog.text


def test_ambiguous_submit_not_retry_and_quit_failure_does_not_undo_acceptance():
    fake=FakeSMTP(failure=('send',TimeoutError(SECRET)))
    with pytest.raises(GmailUncertain) as error:transport(fake).send(draft(),credentials())
    assert error.value.message_id.startswith('<') and SECRET not in str(error.value)
    assert len(fake.messages)==1
    success=FakeSMTP(fail_quit=True)
    assert transport(success).send(draft(),credentials()).status=='accepted'
    assert len(success.messages)==1


def test_partial_and_total_refusal_keep_only_safe_recipient_codes():
    fake=FakeSMTP(refused={'ion@example.test':(550,SECRET.encode())})
    result=transport(fake).send(draft(),credentials())
    assert result.status=='partial' and result.accepted==('ana@example.test',)
    assert result.refused==(('ion@example.test',550),)
    assert SECRET not in repr(result) and SECRET not in journal_text(draft(),result)
    refused=FakeSMTP(failure=('send',smtplib.SMTPRecipientsRefused({'ana@example.test':(550,b'no'),'ion@example.test':(451,b'no')})))
    assert transport(refused).send(draft(),credentials()).status=='rejected'


def test_missing_or_unreadable_attachment_blocks_smtp(tmp_path,monkeypatch):
    from focusdesk.services.mail import attachment_selection
    path=tmp_path/'doc.txt';path.write_text('keep')
    selected=replace(draft(),attachments=attachment_selection([path]));path.unlink()
    fake=FakeSMTP()
    with pytest.raises(Exception):transport(fake).send(selected,credentials())
    assert not fake.calls


def test_profile_credential_lifecycle_no_secret_in_json_or_backup(ws,tmp_path,monkeypatch,caplog):
    from focusdesk.services.backup import create_backup
    monkeypatch.setenv('APPDATA',str(tmp_path/'profile'))
    config=AppConfig();vault=FakeVault();service=GmailService(config,None,secret_store=vault)
    service.configure(provider='gmail',address=credentials().address,display_name='Name',password=SECRET,remember=True)
    key=config.mail.profile_id
    assert config.mail.remembered and vault.get(key)==SECRET
    restarted=GmailService(AppConfig.load(),None,secret_store=vault)
    assert restarted.credentials().password==SECRET
    assert SECRET not in config.path().read_text() and SECRET not in caplog.text
    backup=create_backup(ws)
    with zipfile.ZipFile(backup.path) as archive:assert all(SECRET.encode() not in archive.read(name) for name in archive.namelist())
    assert all(SECRET.encode() not in p.read_bytes() for p in ws.root.rglob('*') if p.is_file())
    service.remove()
    assert not vault.values and not config.mail.address and config.mail.provider=='outlook'
    assert not AppConfig.load().mail.address
    with pytest.raises(GmailError):service.credentials()


def test_unavailable_vault_uses_session_only_without_plaintext_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    config=AppConfig();service=GmailService(config,None,secret_store=FakeVault(False))
    service.configure(provider='gmail',address=credentials().address,display_name='',password=SECRET,remember=True)
    assert not config.mail.remembered and service.credentials().password==SECRET
    with pytest.raises(GmailError):GmailService(AppConfig.load(),None,secret_store=FakeVault(False)).credentials()
    assert all(SECRET.encode() not in p.read_bytes() for p in tmp_path.rglob('*') if p.is_file())
    service.remove();assert not service._session


def test_failed_profile_save_rolls_back_vault_and_memory(tmp_path,monkeypatch):
    import focusdesk.services.gmail as module
    monkeypatch.setenv('APPDATA',str(tmp_path))
    config=AppConfig();vault=FakeVault();service=GmailService(config,None,secret_store=vault)
    service.configure(provider='gmail',address=credentials().address,display_name='',password=SECRET,remember=True)
    before=config.path().read_bytes();metadata=config.mail.model_dump()
    def fail(*a,**kw):raise OSError('disk '+SECRET)
    monkeypatch.setattr(module,'atomic_write_json',fail)
    with pytest.raises(GmailError) as error:
        service.configure(provider='gmail',address='other@domain.example',display_name='',password='new-secret',remember=True)
    assert SECRET not in str(error.value)
    assert config.path().read_bytes()==before and config.mail.model_dump()==metadata
    assert service.credentials().password==SECRET and vault.get(config.mail.profile_id)==SECRET


@pytest.fixture
def gmail_ui(ui,monkeypatch):
    from focusdesk.ui.mail_ui import MailDialog
    fake=FakeSMTP();vault=FakeVault()
    ui.gmail=GmailService(ui.config,ui.bridge,secret_store=vault,transport=transport(fake))
    ui.gmail.configure(provider='gmail',address=credentials().address,display_name='Ștefan',password=SECRET,remember=True)
    monkeypatch.setattr('focusdesk.ui.mail_ui.show_info',lambda *a:None)
    monkeypatch.setattr('focusdesk.ui.mail_ui.show_error',lambda *a:None)
    monkeypatch.setattr('focusdesk.ui.mail_ui.confirm',lambda *a:True)
    dialog=MailDialog(ui.root,ui,ui.ws.get(ui.selected_id))
    dialog.to_var.set('ana@example.test');dialog.cc_var.set('ion@example.test')
    yield ui,dialog,fake
    if dialog.winfo_exists():dialog.destroy()


def test_provider_switch_preserves_snapshot_and_outlook_calendar(gmail_ui,tmp_path):
    app,dialog,fake=gmail_ui
    file=tmp_path/'Äéș.txt';file.write_text('doc');dialog._select_attachments([file])
    body='Edited îäéñ\n  draft';dialog.text.delete('1.0','end');dialog.text.insert('1.0',body)
    before=dialog.collect();calendar=app.ws.settings.outlook.model_dump()
    for index in (0,1,0,1):dialog.provider_box.current(index);dialog._provider_changed();assert dialog.collect()==before
    dialog._open_draft();assert not fake.calls
    assert app.ws.settings.outlook.model_dump()==calendar


def test_gmail_worker_without_outlook_single_submit_and_journal(gmail_ui,monkeypatch):
    app,dialog,fake=gmail_ui
    monkeypatch.setattr(app.outlook,'send_mail',lambda *a,**kw:pytest.fail('Outlook fallback'))
    fake.gate=threading.Event()
    dialog._on_ok();dialog._on_ok();dialog._open_draft()
    assert dialog.pending and app.gmail.busy
    errors=[];app.gmail.send(draft(),lambda _:None,errors.append)
    assert errors[0].kind=='busy'
    fake.gate.set()
    assert pump(app,lambda:not dialog.winfo_exists())
    assert len(fake.messages)==1 and all(name.startswith('focusdesk_') for name in fake.threads)
    note=app.ws.list_notes(dialog.node_id)[0].text
    assert 'Gmail' in note and credentials().address in note and 'ana@example.test' in note
    assert SECRET not in note


def test_gmail_ambiguous_result_blocks_cross_provider_resend(gmail_ui,monkeypatch):
    app,dialog,fake=gmail_ui;fake.failure=('send',TimeoutError(SECRET))
    monkeypatch.setattr(app.outlook,'send_mail',lambda *a,**kw:pytest.fail('Outlook fallback'))
    dialog._on_ok();assert pump(app,lambda:dialog.uncertain)
    assert SECRET not in dialog.message.cget('text')
    dialog.provider_box.current(0);dialog._provider_changed();dialog._on_ok();dialog._open_draft()
    assert len(fake.messages)==1 and dialog.winfo_exists()
    assert 'Gmail' in app.ws.list_notes(dialog.node_id)[0].text


def test_partial_retry_prepares_only_refused_cc_and_waits_for_new_confirmation(gmail_ui):
    app,dialog,fake=gmail_ui
    fake.refused={'ion@example.test':(550,b'no')}
    dialog._on_ok();assert pump(app,lambda:dialog.partial_result is not None)
    dialog._on_ok();assert len(fake.messages)==1
    dialog._retry_refused()
    assert dialog.to_var.get()=='' and dialog.cc_var.get()=='ion@example.test'
    assert len(fake.messages)==1 and not dialog.uncertain
    fake.refused={};dialog._on_ok()
    assert pump(app,lambda:not dialog.winfo_exists())
    assert fake.messages[-1][1]['to_addrs']==['ion@example.test']


def test_failed_auth_preserves_every_field_and_never_switches_provider(gmail_ui,caplog):
    app,dialog,fake=gmail_ui
    fake.failure=('login',smtplib.SMTPAuthenticationError(535,SECRET.encode()))
    original=dialog.collect();dialog._on_ok()
    assert pump(app,lambda:not dialog.pending)
    assert dialog.collect()==original and dialog._provider()=='gmail'
    assert not fake.messages and SECRET not in caplog.text and SECRET not in dialog.message.cget('text')


def test_connection_test_uses_worker_without_saving_or_sending(gmail_ui):
    from focusdesk.ui.gmail_ui import EmailSettingsPanel
    app,dialog,fake=gmail_ui
    panel=EmailSettingsPanel(dialog,app)
    before=app.config.path().read_bytes()
    panel.test();assert panel.pending
    assert pump(app,lambda:not panel.pending)
    assert not fake.messages and fake.login_count==1 and app.config.path().read_bytes()==before
    panel.destroy()


def test_late_smtp_result_does_not_write_to_replacement_workspace(gmail_ui,tmp_path):
    from focusdesk.services.workspace import Workspace
    app,dialog,fake=gmail_ui;fake.gate=threading.Event()
    old=app.ws;other=Workspace.open(tmp_path/'other',create=True)
    dialog._on_ok();app.ws=other;fake.gate.set()
    try:
        assert pump(app,lambda:not dialog.winfo_exists())
        assert not old.list_notes(dialog.node_id) and len(fake.messages)==1
    finally:app.ws=old;other.close()


def test_gmail_journal_failure_does_not_resubmit(gmail_ui,monkeypatch):
    app,dialog,fake=gmail_ui
    def fail(*a,**kw):raise OSError('disk full')
    monkeypatch.setattr(app.ws,'add_note',fail)
    dialog._on_ok();assert pump(app,lambda:not dialog.winfo_exists())
    assert len(fake.messages)==1 and dialog.result['result'].status=='accepted'


def test_native_credential_binding_with_fake_windows_api(monkeypatch):
    import ctypes
    from focusdesk.integrations.credentials import _Credential
    class Api:
        def __init__(self):self.data={};self.freed=0;self.last_error=0
        def CredWriteW(self,pointer,flags):
            item=ctypes.cast(pointer,ctypes.POINTER(_Credential)).contents
            assert item.Type==1 and item.Persist==2 and flags==0
            self.data[item.TargetName]=ctypes.string_at(item.CredentialBlob,item.CredentialBlobSize)
            return 1
        def CredReadW(self,target,kind,flags,pointer):
            assert kind==1 and flags==0
            if target not in self.data:self.last_error=1168;return 0
            raw=self.data[target];blob=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
            item=_Credential();item.CredentialBlob=blob;item.CredentialBlobSize=len(raw)
            self.keep=(item,blob)
            ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(_Credential)))[0]=ctypes.pointer(item)
            return 1
        def CredDeleteW(self,target,kind,flags):
            self.data.pop(target,None);return 1
        def CredFree(self,pointer):self.freed+=1
    api=Api();store=WindowsCredentialStore();monkeypatch.setattr(store,'_api',lambda:api)
    monkeypatch.setattr(ctypes,'get_last_error',lambda:api.last_error,raising=False)
    key=MailSettings().profile_id
    store.set(key,credentials().address,SECRET)
    assert store.get(key)==SECRET and api.freed==1
    assert list(api.data)==['FocusDesk/Gmail/'+key]
    store.delete(key);assert store.get(key) is None
    with pytest.raises(CredentialUnavailable):store.get('../arbitrary-target')


def test_unavailable_old_vault_keeps_removal_reference_and_allows_session(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    config=AppConfig();vault=FakeVault();service=GmailService(config,None,secret_store=vault)
    service.configure(provider='gmail',address=credentials().address,display_name='',password=SECRET,remember=True)
    vault.available=False
    notice=service.configure(provider='gmail',address=credentials().address,display_name='',password='new-session-password',remember=False)
    assert config.mail.credential_pending_removal and not config.mail.remembered
    assert service.credentials().password=='new-session-password'
    with pytest.raises(GmailError):service.remove()
    assert config.mail.address
    vault.available=True;service.remove();assert not vault.values and not service._session


def test_metadata_only_change_does_not_require_opening_vault(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    config=AppConfig();vault=FakeVault();service=GmailService(config,None,secret_store=vault)
    service.configure(provider='gmail',address=credentials().address,display_name='',password=SECRET,remember=True)
    vault.available=False
    service.configure(provider='outlook',address=credentials().address,display_name='',remember=True)
    assert AppConfig.load().mail.provider=='outlook' and config.mail.remembered


def test_nested_gmail_configuration_preserves_composed_draft(gmail_ui,monkeypatch):
    from focusdesk.ui.gmail_ui import EmailSettingsDialog
    app,dialog,fake=gmail_ui;before=dialog.collect()
    app.root.deiconify();app.root.update();dialog.grab_set();seen=[]
    original=EmailSettingsDialog.__init__
    def initialize(self,*args,**kwargs):
        original(self,*args,**kwargs);seen.append(True);self.after(100,self._on_ok)
    monkeypatch.setattr(EmailSettingsDialog,'__init__',initialize)
    dialog._configure_gmail()
    assert seen and dialog.collect()==before and dialog.grab_current() is dialog
    dialog.grab_release()


def test_missing_configuration_offers_settings_without_losing_draft(gmail_ui):
    app,dialog,fake=gmail_ui
    app.gmail.remove();dialog._provider_choices('gmail');dialog._provider_changed()
    before=dialog.collect();dialog._on_ok()
    assert dialog.collect()==before and not dialog.pending and not fake.calls
    assert dialog.configure_btn.winfo_manager()=='grid'


def test_export_eml_is_local_and_keeps_uncertain_send_locked(gmail_ui,tmp_path,monkeypatch):
    app,dialog,fake=gmail_ui
    fake.failure=('send',TimeoutError(SECRET))
    dialog._on_ok();assert pump(app,lambda:dialog.uncertain)
    target=tmp_path/'saved.eml'
    monkeypatch.setattr('focusdesk.ui.mail_ui.filedialog.asksaveasfilename',lambda **kw:str(target))
    dialog._save_eml();assert pump(app,lambda:not dialog.pending)
    assert target.is_file() and len(fake.messages)==1 and dialog.uncertain
    assert str(dialog.ok_btn.cget('state'))=='disabled'


def test_connection_settings_available_without_workspace_and_readonly(ui):
    from focusdesk.ui.settings_dialog import SettingsDialog
    ui.ws.repo.read_only=True
    settings=SettingsDialog(ui.root,ui)
    assert settings.ok_btn.instate(['disabled']) and settings.email_panel is not None
    settings.destroy();ui.ws.repo.read_only=False
    workspace=ui.ws;ui.ws=None
    try:
        settings=SettingsDialog(ui.root,ui)
        assert settings.email_panel is not None
        settings.destroy()
    finally:ui.ws=workspace


def test_return_in_mail_profile_field_does_not_save_workspace_or_close_settings(ui):
    from focusdesk.ui.settings_dialog import SettingsDialog
    ui.root.deiconify();ui.root.update()
    settings=SettingsDialog(ui.root,ui);settings.nb.select(settings.email_panel.master.master)
    saves=[];settings.bind('<Return>',lambda event:saves.append('workspace-save'))
    settings.email_panel.password_entry.focus_force();ui.root.update()
    settings.email_panel.password_entry.event_generate('<Return>');ui.root.update()
    assert not saves and settings.winfo_exists()
    settings.destroy()
