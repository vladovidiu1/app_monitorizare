import pytest
from pydantic import ValidationError as PydanticError

from focusdesk.ai.protocol import Proposal
from focusdesk.domain.models import Kind
from focusdesk.errors import ValidationError
from focusdesk.services.ai_actions import ActionContext, apply_proposal


@pytest.mark.parametrize("action,title,text", [("add_note", "", "Notă AI"),
    ("create_subtask", "Pas nou", "Descriere"), ("set_next_action", "", "Verifică rezultatul")])
def test_proposal_writes_through_workspace_and_persists(ws, action, title, text):
    task = ws.create_node(Kind.TASK, "Țintă")
    context = ActionContext.capture(ws, task.id, action)
    proposal = Proposal(action=action, title=title, text=text)
    apply_proposal(ws, context, proposal)
    ws.reload()
    if action == "add_note":
        assert ws.list_notes(task.id)[0].text == text
    elif action == "create_subtask":
        assert any(n.title == title and n.parent_id == task.id for n in ws.nodes.values())
    else:
        assert ws.get(task.id).next_action == text


def test_stale_wrong_action_and_wrong_workspace_rejected(ws):
    task = ws.create_node(Kind.TASK, "T")
    context = ActionContext.capture(ws, task.id, "add_note")
    with pytest.raises(ValidationError, match="altă operație"):
        apply_proposal(ws, context, Proposal(action="set_next_action", title="", text="Pas"))
    ws.update_node(task.id, title="Modificat")
    with pytest.raises(ValidationError, match="schimbat"):
        apply_proposal(ws, context, Proposal(action="add_note", title="", text="Notă"))
    assert ws.list_notes(task.id) == []


@pytest.mark.parametrize("payload", [
    {"action": "shell", "title": "", "text": "cmd.exe"},
    {"action": "add_note", "title": "", "text": " ", "node_id": "other"},
    {"action": "create_subtask", "title": "", "text": "abc"},
    {"action": "set_next_action", "title": "ignored?", "text": "abc"},
])
def test_valid_json_does_not_imply_valid_action(payload):
    with pytest.raises(PydanticError):
        Proposal.model_validate(payload)


def test_folder_cannot_receive_next_action(ws):
    folder = ws.create_node(Kind.FOLDER, "F")
    context = ActionContext.capture(ws, folder.id, "set_next_action")
    with pytest.raises(ValidationError, match="task-uri"):
        apply_proposal(ws, context, Proposal(action="set_next_action", title="", text="x"))


def test_description_change_and_external_edits_invalidate_proposal(ws):
    task = ws.create_node(Kind.TASK, "T", description="Inițial")
    context = ActionContext.capture(ws, task.id, "add_note")
    ws.set_description(task.id, "Editat după generare")
    with pytest.raises(ValidationError, match="schimbat"):
        apply_proposal(ws, context, Proposal(action="add_note", title="", text="Notă"))
    context = ActionContext.capture(ws, task.id, "add_note")
    (ws.repo.dirs[task.id] / "description.md").write_text("Editare externă", encoding="utf-8")
    with pytest.raises(ValidationError, match="schimbat"):
        apply_proposal(ws, context, Proposal(action="add_note", title="", text="Notă"))
    assert ws.list_notes(task.id) == []
