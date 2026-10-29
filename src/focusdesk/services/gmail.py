"""Profile/credential lifecycle and Gmail jobs, independent of workspace/calendar."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from ..domain.mail import MailSettings
from ..integrations.credentials import WindowsCredentialStore, CredentialUnavailable
from ..integrations.gmail import (GmailCredentials,GmailTransport,GmailResult,GmailError,
                                  account_address,normalize_password,mime_message)
from ..i18n import tr
from ..storage.atomic import atomic_write_json, atomic_write_bytes


class GmailService:
    def __init__(self,config,bridge,*,secret_store=None,transport=None):
        self.config,self.bridge=config,bridge
        self.store=secret_store if secret_store is not None else WindowsCredentialStore()
        self.transport=transport if transport is not None else GmailTransport()
        self._session={}
        self.busy=False
        self.job=None

    def _persist(self,settings):
        snapshot=self.config.model_copy(update={'mail':settings})
        try:atomic_write_json(self.config.path(),snapshot.model_dump(mode='json'),keep_backup=False)
        except Exception:raise GmailError('profile_save') from None
        self.config.mail=settings

    def _stored(self,settings):
        if settings.profile_id in self._session:return self._session[settings.profile_id]
        if settings.remembered:
            try:return self.store.get(settings.profile_id)
            except CredentialUnavailable:raise GmailError('secure_unavailable') from None
        return None

    def credentials(self,*,address=None,display_name=None,password=None):
        settings=self.config.mail
        address=account_address(settings.address if address is None else address)
        name=settings.display_name if display_name is None else display_name
        secret=normalize_password(password) if password else (self._stored(settings) if address==settings.address else None)
        if not secret:raise GmailError('not_configured')
        return GmailCredentials(address,secret,name)

    def configure(self,*,provider,address,display_name,password='',remember=False):
        if self.busy:raise GmailError('busy')
        old=self.config.mail
        address=account_address(address) if address.strip() else ''
        if provider=='gmail' and not address:raise GmailError('account')
        if provider not in ('outlook','gmail'):raise GmailError('account')
        if not password and address==old.address and remember==old.remembered:
            self._persist(old.model_copy(update={'provider':provider,'display_name':' '.join(display_name.split())}))
            return tr('gmail.settings_saved')
        secret=normalize_password(password) if password else (self._stored(old) if address==old.address else None)
        new=MailSettings(provider=provider,profile_id=old.profile_id,address=address,
                         display_name=' '.join(display_name.split()),remembered=False)
        previous_vault=None;changed_vault=False;memory_only=False
        try:
            if remember and secret:
                try:
                    previous_vault=self.store.get(old.profile_id)
                    self.store.set(old.profile_id,address,secret);changed_vault=True
                    new.remembered=True
                except CredentialUnavailable:
                    memory_only=True
                    new.credential_pending_removal=old.remembered or old.credential_pending_removal
            elif old.remembered or old.credential_pending_removal:
                try:
                    previous_vault=self.store.get(old.profile_id)
                    self.store.delete(old.profile_id);changed_vault=True
                except CredentialUnavailable:
                    # Never orphan a previously stored credential or claim it was erased.
                    memory_only=True;new.credential_pending_removal=True
            self._persist(new)
        except Exception as exc:
            if changed_vault:
                try:
                    if previous_vault:self.store.set(old.profile_id,old.address,previous_vault)
                    else:self.store.delete(old.profile_id)
                except CredentialUnavailable:raise GmailError('credential_reconcile') from None
            if isinstance(exc,GmailError):raise
            raise GmailError('secure_unavailable') from None
        self._session.pop(old.profile_id,None)
        if secret:self._session[new.profile_id]=secret
        notice=tr('gmail.session_only') if memory_only or (secret and not new.remembered) else tr('gmail.settings_saved')
        if new.credential_pending_removal:notice+='\n'+tr('gmail.pending_removal')
        return notice

    def remove(self):
        if self.busy:raise GmailError('busy')
        old=self.config.mail;previous=None
        try:
            if old.remembered or old.credential_pending_removal:
                previous=self.store.get(old.profile_id)
                self.store.delete(old.profile_id)
            self._persist(MailSettings())
        except Exception as exc:
            if previous:
                try:self.store.set(old.profile_id,old.address,previous)
                except CredentialUnavailable:raise GmailError('credential_reconcile') from None
            if isinstance(exc,GmailError):raise
            raise GmailError('secure_unavailable') from None
        self._session.clear()

    def _submit(self,work,on_done,on_error):
        if self.busy:on_error(GmailError('busy'));return None
        self.busy=True
        def perform(token):
            try:return work()
            except GmailError as exc:return exc
            except Exception:return GmailError('message')
        def deliver(value):
            self.busy=False
            if isinstance(value,BaseException):on_error(value)
            else:on_done(value)
        try:self.job=self.bridge.submit(perform,deliver,name='gmail')
        except Exception:
            self.busy=False;on_error(GmailError('message'));return None
        return self.job

    def send(self,draft,on_done,on_error,*,credentials=None):
        try:credentials=credentials or self.credentials()
        except GmailError as exc:on_error(exc);return None
        # Copy editable collections before crossing the Tk boundary.
        snapshot=replace(draft,to=list(draft.to),cc=list(draft.cc),attachments=list(draft.attachments))
        return self._submit(lambda:self.transport.send(snapshot,credentials),on_done,on_error)

    def test(self,credentials,on_done,on_error):
        return self._submit(lambda:self.transport.test(credentials),on_done,on_error)

    def clear_session(self):
        self._session.clear()


def result_notice(result:GmailResult):
    key={'accepted':'accepted','partial':'partial','rejected':'rejected','uncertain':'uncertain'}[result.status]
    text=tr('gmail.result.'+key,account=result.account)
    if result.accepted:text+='\n'+tr('gmail.accepted_addresses',addresses=', '.join(result.accepted))
    if result.refused:text+='\n'+tr('gmail.refused_addresses',addresses=', '.join(f'{a} ({code})' for a,code in result.refused))
    return text


def journal_text(draft,result):
    return tr('gmail.journal',outcome=result_notice(result),account=result.account,
              to=', '.join(draft.to),cc=', '.join(draft.cc) or '—',subject=draft.subject,
              at=result.at,message_id=result.message_id,
              attachments='; '.join(item.name for item in draft.attachments) or tr('services.mail.fara_atasamente'))


def save_eml(path,draft,address,display_name=''):
    message=mime_message(draft,address,display_name)
    atomic_write_bytes(Path(path),message.as_bytes(),keep_backup=False)
