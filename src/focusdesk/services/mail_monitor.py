"""Scanare persistentă. Scrierile sunt delegate exclusiv fațadei Workspace."""

from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

from ..domain.mail_monitor import FolderCursor, MailHeader, MailRecord

UTC = timezone.utc


def content_hash(record: MailRecord) -> str:
    header = record.header.model_dump(mode="json", exclude={"entry_id", "folder_id", "modified_at", "search_key"})
    payload = {"header": header, "body": record.body, "attachments": [v.model_dump() for v in record.attachments]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def mail_fingerprint(record: MailRecord) -> str:
    return f"{record.content_version}:{content_hash(record)}"


class MailMonitorService:
    def __init__(self, ws):
        self.ws = ws

    def plan(self, now=None, budget=None):
        now = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
        config = self.ws.settings.mail_monitor
        if not config.enabled or not config.folders or self.ws.read_only:
            return None
        state = self.ws.mail_state()
        folder = config.folders[state.next_folder % len(config.folders)]
        key = folder.store_id + ":" + folder.folder_id
        cursor = state.cursors.get(key)
        if cursor is None:
            tz = ZoneInfo(self.ws.settings.timezone)
            start = datetime.combine(config.first_since, time.min, tzinfo=tz).astimezone(UTC) if config.first_since else now - timedelta(days=config.first_days)
            end = min(now, datetime.combine(config.first_until + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)) if config.first_until else now
            cursor = FolderCursor(cutover=now.isoformat(), initial_from=start.isoformat(), initial_to=end.isoformat(), watermark=now.isoformat())
            state.cursors[key] = cursor
        if cursor.initial_done and cursor.window_from is None:
            cursor.window_from = (datetime.fromisoformat(cursor.watermark) - timedelta(days=1)).isoformat()
            cursor.window_to = now.isoformat()
            cursor.offset = 0
        self.ws.save_mail_state(state)
        remaining = config.first_max - cursor.initial_count if not cursor.initial_done else config.page_size
        return {"key": key, "store_id": folder.store_id, "folder_id": folder.folder_id,
                "phase": "incremental" if cursor.initial_done else "initial", "cutover": cursor.cutover,
                "from": cursor.window_from if cursor.initial_done else cursor.initial_from,
                "to": cursor.window_to if cursor.initial_done else cursor.initial_to,
                "offset": cursor.offset, "limit": max(1, min(config.page_size, budget or config.max_per_check, remaining))}

    def details_needed(self, plan, page):
        state = self.ws.mail_state()
        out = []
        for raw in page["headers"]:
            header = MailHeader.model_validate(raw)
            known = self.ws.mail_get(header.identity)
            eligible = plan["phase"] == "initial" or header.received_at >= datetime.fromisoformat(plan["cutover"]) or known is not None
            if eligible and header.conversation_key not in state.ignored_conversations:
                if known is None or not known.body_loaded or known.header.modified_at != header.modified_at:
                    out.append({"store_id": header.store_id, "entry_id": header.entry_id})
        return out

    def commit(self, plan, page, details):
        state = self.ws.mail_state()
        cursor = state.cursors[plan["key"]]
        if cursor.offset != plan["offset"] or (plan["phase"] == "initial") == cursor.initial_done:
            raise ValueError("Checkpoint-ul scanării s-a schimbat; reîncearcă pagina.")
        full = {MailHeader.model_validate(value["header"]).identity: value for value in details}
        imported = 0
        for raw in page["headers"]:
            header = MailHeader.model_validate(raw)
            previous = self.ws.mail_get(header.identity)
            if plan["phase"] != "initial" and header.received_at < datetime.fromisoformat(plan["cutover"]) and previous is None:
                continue  # overlap must not defeat the explicit first-import cap
            ignored = header.conversation_key in state.ignored_conversations
            record = previous.model_copy(deep=True) if previous else MailRecord(id=header.identity, header=header)
            record.header = header
            if header.identity in full:
                detail = full[header.identity]
                record.header = MailHeader.model_validate(detail["header"])
                record.body = detail["body"][:12000]
                record.body_loaded = True
                record.body_truncated = detail.get("body_truncated", False)
                from ..domain.mail_monitor import AttachmentMeta
                record.attachments = [AttachmentMeta.model_validate(a) for a in detail.get("attachments", [])[:20]]
            elif previous is None and not ignored:
                raise ValueError("Detaliile unei scrisori lipsesc; checkpoint-ul nu avansează.")
            fingerprint = content_hash(record)
            if previous and fingerprint != previous.content_hash:
                record.content_version += 1
                if previous.state not in ("rejected", "ignored", "handled", "informational"):
                    record.state = "pending"
                    record.projection = None
            record.content_hash = fingerprint
            if ignored:
                if record.state != "ignored":
                    record.suspended_state = record.state
                record.state = "ignored"
            self.ws.save_mail_record(record)
            imported += previous is None
        cursor.offset = page["next_offset"]
        if not cursor.initial_done:
            cursor.initial_count += len(page["headers"])
            if page["done"] or cursor.initial_count >= self.ws.settings.mail_monitor.first_max:
                cursor.initial_done = True
                cursor.limit_reached = not page["done"]
                cursor.offset = 0
        elif page["done"]:
            cursor.watermark = cursor.window_to
            cursor.window_from = cursor.window_to = None
            cursor.offset = 0
        state.next_folder += 1
        self.ws.save_mail_state(state)  # last: replay after a crash deduplicates already written records
        return imported

    def ignore_conversation(self, message_id, ignore=True):
        message = self.ws.mail_get(message_id)
        state = self.ws.mail_state()
        key = message.header.conversation_key
        values = set(state.ignored_conversations)
        values.add(key) if ignore else values.discard(key)
        state.ignored_conversations = sorted(values)
        self.ws.save_mail_state(state)
        for record in self.ws.mail_records():
            if record.header.conversation_key == key:
                if ignore:
                    if record.state != "ignored":
                        record.suspended_state = record.state
                    record.state = "ignored"
                elif record.state == "ignored":
                    record.state = record.suspended_state or "pending"
                    record.suspended_state = None
                self.ws.save_mail_record(record)

    def confirmed_candidates(self, message):
        ids = list(message.confirmed_task_ids)
        for record in self.ws.mail_records():
            if record.header.conversation_key == message.header.conversation_key:
                ids.extend(record.confirmed_task_ids)
        return [node_id for node_id in dict.fromkeys(ids) if node_id in self.ws.nodes]
