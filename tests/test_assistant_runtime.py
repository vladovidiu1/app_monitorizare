import json
from pathlib import Path
from uuid import uuid4

import pytest

from focusdesk.ai.protocol import EngineSettings, Request
from focusdesk.ai.runtime import LocalModel, assistant_schema
from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.services.assistant_context import build_context
from focusdesk.services.assistant_proposals import validate_reply
from focusdesk.domain.models import Kind
from focusdesk.errors import ValidationError


def test_readonly_and_action_intents_have_different_grammars():
    node_id = str(uuid4())
    key = "task:" + node_id
    readonly = assistant_schema([key], [node_id], "resume")
    assert readonly["properties"]["actions"] == {"const": []}
    assert readonly["properties"]["email"] == {"const": None}
    steps = assistant_schema([key], [node_id], "steps")
    assert steps["properties"]["actions"]["minItems"] == 1
    email = assistant_schema([key], [node_id], "email")
    assert "$ref" in email["properties"]["email"]
    assert email["$defs"]["AnswerPart"]["properties"]["sources"]["items"]["enum"] == [key]


def test_exact_token_budget_drops_history_and_low_ranked_records():
    pytest.importorskip("llama_cpp")
    from llama_cpp.llama_chat_format import Jinja2ChatFormatter

    node_id = str(uuid4())
    key = "task:" + node_id
    class FakeModel:
        def tokenize(self, data, **kwargs):
            self.text = data.decode()
            return list(data)  # conservative byte tokenizer, deliberately overestimates real BPE
        def create_completion(self, prompt, max_tokens, **kwargs):
            assert len(prompt) + max_tokens + 16 <= 4096
            self.prompt_tokens = len(prompt)
            payload = {"answer": [{"text": "Date din context.", "sources": [key]}], "actions": [], "email": None}
            return {"choices": [{"finish_reason": "stop", "text": json.dumps(payload)}],
                    "usage": {"prompt_tokens": len(prompt), "completion_tokens": 30, "total_tokens": len(prompt) + 30}}
    runtime = LocalModel.__new__(LocalModel)
    runtime.settings = EngineSettings()
    runtime.model = FakeModel()
    template = (Path(__file__).parent / "fixtures/qwen3_chat_template.jinja").read_text(encoding="utf-8")
    runtime.formatter = Jinja2ChatFormatter(template, eos_token="<|im_end|>", bos_token="")
    records = [{"key": key if i == 0 else "task:" + str(uuid4()), "node_id": node_id, "data": {"text": "x" * 600}} for i in range(20)]
    context = {"records": records, "history": [{"text": "old-history" * 100} for _ in range(6)]}
    result = runtime.generate(Request(request_id=str(uuid4()), action="assistant", instruction="Rezumă.", context=json.dumps(context)))
    assert 0 < len(result._context_keys) < len(records)
    assert "old-history" not in runtime.model.text
    assert result._usage["prompt_tokens"] == runtime.model.prompt_tokens


def test_oversized_question_fails_before_generation():
    pytest.importorskip("llama_cpp")
    from llama_cpp.llama_chat_format import Jinja2ChatFormatter
    class FakeModel:
        def tokenize(self, data, **kwargs):
            return list(data)
        def create_completion(self, **kwargs):
            pytest.fail("must not infer when the reserve does not fit")
    runtime = LocalModel.__new__(LocalModel)
    runtime.settings = EngineSettings(context=2048)
    runtime.model = FakeModel()
    template = (Path(__file__).parent / "fixtures/qwen3_chat_template.jinja").read_text(encoding="utf-8")
    runtime.formatter = Jinja2ChatFormatter(template, eos_token="<|im_end|>", bos_token="")
    with pytest.raises(ValueError, match="rezerva"):
        runtime.generate(Request(request_id=str(uuid4()), action="assistant", instruction="x" * 4000, context='{"records":[]}'))


def test_readonly_intent_and_omitted_source_are_checked_in_parent(ws):
    node = ws.create_node(Kind.TASK, "T")
    bundle = build_context(ws, "task", node.id, "")
    key = f"task:{node.id}"
    reply = AssistantReply.model_validate({"answer": [{"text": "Date", "sources": [key]}], "actions": [
        {"kind": "add_note", "node_id": node.id, "text": "Nu aplica", "reason": "Date neîncredere", "sources": [key]}]})
    with pytest.raises(ValidationError, match="consultare"):
        validate_reply(ws, bundle, reply, [key], "resume")
    with pytest.raises(ValidationError, match="surs"):
        validate_reply(ws, bundle, reply, [], "actions")
    assert ws.list_notes(node.id) == []
