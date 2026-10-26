from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from focusdesk.integrations import mail_read


class Accessor:
    def __init__(self, values):
        self.values = values
    def GetProperty(self, name):
        if name[-10:] not in self.values:
            raise LookupError("property unavailable")
        return self.values[name[-10:]]


class Item:
    Class = 43
    EntryID = "entry"
    Subject = "Test"
    ConversationID = "thread"
    SenderEmailType = "EX"
    SenderName = "Nume afișat, NU o adresă"
    SenderEmailAddress = "/O=ORG/OU=EXCHANGE/CN=LEGACY"
    SentOn = ReceivedTime = LastModificationTime = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    Parent = SimpleNamespace(EntryID="folder")
    Attachments = SimpleNamespace(Count=1, Item=lambda i: SimpleNamespace(FileName="danger.exe", Size=123, Type=1))

    def __init__(self):
        self.reads = 0
        self.PropertyAccessor = Accessor({"0x1035001F": "<unique@example.org>", "0x300B0102": b"key"})
        self.Sender = SimpleNamespace(GetExchangeUser=lambda: SimpleNamespace(PrimarySmtpAddress="real.sender@example.org"),
            GetExchangeDistributionList=lambda: None, PropertyAccessor=Accessor({}))

    @property
    def Body(self):
        self.reads += 1
        return "Secret local body"

    @property
    def UnRead(self):
        raise AssertionError("Unread must not be used as processing state")

    def Save(self):
        pytest.fail("read must not save Outlook item")

    def Move(self, *_):
        pytest.fail("read must not move Outlook item")

    def Delete(self):
        pytest.fail("read must not delete Outlook item")


def test_exchange_smtp_is_real_and_never_derived_from_display_name():
    item = Item()
    assert mail_read.smtp_address(item) == "real.sender@example.org"
    item.Sender = SimpleNamespace(PropertyAccessor=Accessor({}))
    assert mail_read.smtp_address(item) is None
    item.PropertyAccessor = Accessor({"0x5D01001F": "direct@example.org"})
    assert mail_read.smtp_address(item) == "direct@example.org"


def test_metadata_page_and_details_are_json_only_and_read_only(monkeypatch):
    item = Item()
    class Table:
        def __init__(self):
            self.EndOfTable = False
        def Sort(self, *_):
            pass
        def GetNextRow(self):
            self.EndOfTable = True
            return SimpleNamespace(Item=lambda key: {"MessageClass": "IPM.Note", "EntryID": "entry"}[key])
    table = Table()
    queries = []
    folder = SimpleNamespace(GetTable=lambda query: (queries.append(query), table)[1])
    ns = SimpleNamespace(GetFolderFromID=lambda *a: folder, GetItemFromID=lambda *a: item)
    monkeypatch.setattr(mail_read, "namespace", lambda backend: ns)
    plan = {"store_id": "store", "folder_id": "folder", "phase": "initial", "from": "2026-10-25T00:00:00+00:00",
            "to": "2026-10-27T00:00:00+00:00", "offset": 0, "limit": 10}
    page = mail_read.scan_page(None, plan)
    json.dumps(page)
    assert item.reads == 0 and "0x0E060040" in queries[0]
    details = mail_read.read_details(None, [{"store_id": "store", "entry_id": "entry"}])
    json.dumps(details)
    assert item.reads == 1
    assert details[0]["attachments"] == [{"filename": "danger.exe", "size": 123, "type": 1}]
    assert "content" not in details[0]["attachments"][0]


def test_native_errors_do_not_expose_body_or_original_exception(monkeypatch):
    class Broken(Item):
        @property
        def Body(self):
            raise RuntimeError("PRIVATE BODY CONTENT MUST NOT APPEAR")
    monkeypatch.setattr(mail_read, "namespace", lambda backend: SimpleNamespace(GetItemFromID=lambda *a: Broken()))
    with pytest.raises(RuntimeError) as error:
        mail_read.read_details(None, [{"store_id": "store", "entry_id": "entry"}])
    assert "PRIVATE BODY" not in str(error.value) and error.value.__suppress_context__
