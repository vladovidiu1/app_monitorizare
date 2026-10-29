"""Explicit Gmail SMTP operations. No inbox, COM, credentials-on-disk or retries."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, formataddr, make_msgid
import mimetypes
from pathlib import Path
import smtplib
import socket
import ssl

from ..errors import FocusDeskError, ValidationError
from ..i18n import tr
from ..services.mail import MailDraft, validate_attachments, parse_addresses, clean_subject


@dataclass(frozen=True)
class GmailCredentials:
    address: str
    password: str = field(repr=False)
    display_name: str = ''


@dataclass(frozen=True)
class GmailResult:
    status: str
    account: str
    accepted: tuple[str,...]
    refused: tuple[tuple[str,int],...]
    message_id: str
    at: str = field(default_factory=lambda:datetime.now(timezone.utc).isoformat())


class GmailError(FocusDeskError):
    """Only a known key and numeric SMTP code may cross the worker/log boundary."""
    def __init__(self,kind,code=None):
        self.kind=kind
        self.code=code if isinstance(code,int) and 100<=code<=599 else None
        super().__init__(tr('gmail.error.'+kind)+(tr('gmail.smtp_code',code=self.code) if self.code else ''))


class GmailUncertain(GmailError):
    def __init__(self,message_id):
        self.message_id=message_id
        super().__init__('uncertain')


def normalize_password(value):
    # Google presents groups separated by ASCII spaces. Do not strip other characters.
    value=value.replace(' ','')
    if not value or any(ord(c)<32 or ord(c)==127 for c in value):raise GmailError('password')
    return value


def account_address(value):
    try:addresses=parse_addresses(value)
    except ValidationError:raise GmailError('account') from None
    if len(addresses)!=1 or value.strip()!=addresses[0]:raise GmailError('account')
    try:addresses[0].encode('ascii')
    except UnicodeError:raise GmailError('account') from None
    return addresses[0]


def mime_message(draft:MailDraft,address:str,display_name:str='',*,message_id=None):
    """Read every selected document before touching SMTP. Never emit an incomplete message."""
    address=account_address(address)
    message=EmailMessage(policy=SMTP)
    message['From']=formataddr((clean_subject(display_name),address))
    message['To']=', '.join(draft.to)
    if draft.cc:message['Cc']=', '.join(draft.cc)
    message['Subject']=clean_subject(draft.subject)
    message['Date']=format_datetime(datetime.now(timezone.utc))
    message['Message-ID']=message_id or make_msgid(domain=address.split('@')[1])
    message.set_content(draft.body)
    for item in validate_attachments(draft.attachments):
        try:data=Path(item.path).read_bytes()
        except OSError:raise GmailError('attachment') from None
        content_type=mimetypes.guess_type(item.name)[0] or 'application/octet-stream'
        major,minor=content_type.split('/',1)
        message.add_attachment(data,maintype=major,subtype=minor,filename=item.name)
    return message


class GmailTransport:
    def __init__(self,*,port=465,timeout=25,smtp_ssl=None,smtp_starttls=None):
        if port not in (465,587):raise ValueError('TLS SMTP port required')
        self.port,self.timeout=port,timeout
        self.smtp_ssl=smtp_ssl or smtplib.SMTP_SSL
        self.smtp_starttls=smtp_starttls or smtplib.SMTP

    def _connect(self,credentials):
        context=ssl.create_default_context()
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        client=None
        try:
            if self.port==465:
                client=self.smtp_ssl('smtp.gmail.com',465,timeout=self.timeout,context=context)
            else:
                client=self.smtp_starttls('smtp.gmail.com',587,timeout=self.timeout)
                client.ehlo()
                try:client.starttls(context=context);client.ehlo()
                except Exception:raise GmailError('tls') from None
            client.login(credentials.address,credentials.password)
            return client
        except Exception:
            if client is not None:self._close(client)
            raise

    @staticmethod
    def _close(client):
        try:client.quit()
        except Exception:
            try:client.close()
            except Exception:pass

    @staticmethod
    def _error(exc):
        if isinstance(exc,GmailError):return exc
        code=getattr(exc,'smtp_code',None)
        reply=getattr(exc,'smtp_error',b'')
        if isinstance(reply,str):reply=reply.encode('utf-8',errors='replace')
        if isinstance(exc,smtplib.SMTPResponseException) and (code in (421,450,451,452,454) or
                any(token in reply.lower() for token in (b'quota',b'rate limit',b'daily user sending',b'too many',b'limit exceeded'))):
            return GmailError('limit',code)
        if isinstance(exc,smtplib.SMTPAuthenticationError):return GmailError('auth_policy' if code==534 else 'auth',code)
        if isinstance(exc,ssl.SSLError):return GmailError('tls',code)
        if isinstance(exc,(TimeoutError,socket.timeout)):return GmailError('timeout')
        if isinstance(exc,smtplib.SMTPResponseException):
            return GmailError('message',code)
        if isinstance(exc,smtplib.SMTPNotSupportedError):return GmailError('message',code)
        if isinstance(exc,(socket.gaierror,ConnectionError,OSError)):return GmailError('network')
        return GmailError('message',code)

    def test(self,credentials):
        client=None
        try:client=self._connect(credentials)
        except Exception as exc:raise self._error(exc) from None
        finally:
            if client is not None:self._close(client)
        return True

    def send(self,draft,credentials):
        client=None;submitting=False
        message=mime_message(draft,credentials.address,credentials.display_name)
        message_id=str(message['Message-ID'])
        recipients=tuple(dict.fromkeys([*draft.to,*draft.cc]))
        try:
            client=self._connect(credentials)
            submitting=True
            refused=client.send_message(message,from_addr=credentials.address,to_addrs=list(recipients))
            codes=tuple((a,int(refused[a][0])) for a in recipients if a in refused)
            accepted=tuple(a for a in recipients if a not in refused)
            return GmailResult('partial' if codes and accepted else 'rejected' if codes else 'accepted',
                               credentials.address,accepted,codes,message_id)
        except smtplib.SMTPRecipientsRefused as exc:
            return GmailResult('rejected',credentials.address,(),tuple((a,int(exc.recipients[a][0])) for a in recipients if a in exc.recipients),message_id)
        except (smtplib.SMTPResponseException,smtplib.SMTPNotSupportedError) as exc:
            raise self._error(exc) from None
        except Exception as exc:
            if submitting:raise GmailUncertain(message_id) from None
            raise self._error(exc) from None
        finally:
            # A lost QUIT response cannot undo the server's known acceptance of DATA.
            if client is not None:self._close(client)
