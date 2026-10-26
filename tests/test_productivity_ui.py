import json
from uuid import uuid4
from test_ai_ui import ui
from test_mail_ui import pump

from focusdesk.ai.protocol import Response
from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.services.ai_productivity import MAIL_MODES
from focusdesk.ui.mail_ui import MailDialog
from focusdesk.ui.productivity_ui import ProductivityWindow


def capture(ui, monkeypatch):
    data = {}
    ui.config.ai.enabled = True
    def request(*args, **kwargs):
        data.update(id=str(uuid4()), callback=args[-1], context=json.loads(args[3]), intent=kwargs['intent'])
        return data['id']
    monkeypatch.setattr(ui.ai, 'request', request)
    monkeypatch.setattr(ui.outlook, 'send_mail', lambda *a, **k: (_ for _ in ()).throw(AssertionError('automatic send')))
    return data


def test_mail_dialog_ai_generates_editable_preview_without_send(ui, monkeypatch):
    captured = capture(ui, monkeypatch)
    dialog = MailDialog(ui.root, ui, ui.ws.get(ui.selected_id))
    assert tuple(dialog.ai_mode.get() for _ in [0]) == (MAIL_MODES[0],)
    dialog.to_var.set('valid@example.org')
    dialog._generate_ai()
    window = next(view for view in ui.ai.views if isinstance(view, ProductivityWindow))
    window.generate()
    pump(ui, lambda:'callback' in captured)
    key = 'task:' + ui.selected_id
    reply = AssistantReply(answer=[{'text':'Ciornă','sources':[key]}], email={
        'node_id':ui.selected_id,'subject':'Clarificare','body':'Te rog să clarifici cerința.', 'reason':'Cerere', 'sources':[key]})
    captured['callback'](Response(request_id=captured['id'],kind='result',assistant=reply,context_keys=list(window.bundle.sources)))
    assert window.reply and dialog.subject_var.get() != 'Clarificare'
    window.text.insert('end', '\nMulțumesc.')
    monkeypatch.setattr('focusdesk.ui.productivity_ui.confirm', lambda *a:True)
    window.use()
    assert dialog.subject_var.get() == 'Clarificare'
    assert 'Mulțumesc.' in dialog.text.get('1.0','end')
    assert dialog.to_var.get() == 'valid@example.org'
    assert dialog.result is None  # no collect / no send
    dialog.destroy()


def test_day_uses_planner_preview_today_only_without_creating_sessions(ui, monkeypatch):
    captured = capture(ui, monkeypatch)
    window = ProductivityWindow(ui,'day')
    window.generate()
    pump(ui,lambda:'callback' in captured)
    key = 'task:' + ui.selected_id
    reply=AssistantReply(answer=[{'text':'Necesită estimare.', 'sources':[key]}])
    captured['callback'](Response(request_id=captured['id'],kind='result',assistant=reply,context_keys=list(window.bundle.sources)))
    calls = []
    def preview(dialog):
        calls.append((dialog.from_var.get(),dialog.to_var.get(),dialog.tasks_tv.selection()))
        dialog.destroy()
    monkeypatch.setattr('focusdesk.ui.planning.PlannerDialog.run',preview)
    window.use()
    assert calls[0][0] == calls[0][1]
    assert ui.selected_id in calls[0][2]
    assert ui.ws.repo.sessions.list_all() == []
    window.destroy()


def test_numeric_report_without_ai_can_copy_and_prepare_standalone_mail(ui, monkeypatch):
    captured = capture(ui,monkeypatch)
    ui.config.ai.enabled = False
    window=ProductivityWindow(ui,'report')
    window.generate(only_data=True)
    pump(ui,lambda:window.report is not None)
    assert window.report['actual_seconds'] == 0
    assert 'callback' not in captured
    window.copy()
    assert '0 secunde' in window.clipboard_get()
    drafts=[]
    monkeypatch.setattr(ui,'compose_mail',lambda *a,**kw:drafts.append(kw))
    window.use()
    assert drafts[0]['standalone'] and drafts[0]['ai_draft'].to == []
    window.destroy()
    dialog=MailDialog(ui.root,ui,None)
    assert dialog.to_var.get() == ''
    assert dialog.result is None
    dialog.destroy()


def test_cancel_and_workspace_switch_ignore_late_reply(ui,monkeypatch):
    captured=capture(ui,monkeypatch)
    window=ProductivityWindow(ui,'day')
    window.generate()
    pump(ui,lambda:'callback' in captured)
    window.cancel()
    key='task:'+ui.selected_id
    captured['callback'](Response(request_id=captured['id'],kind='result',assistant=AssistantReply(answer=[{'text':'Prioritate','sources':[key]}]),context_keys=[key]))
    assert window.reply is None and window.selected == []
    ui.ai.invalidate_workspace()
    assert window.closed
