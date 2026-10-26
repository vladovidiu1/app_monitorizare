"""Backend read-only fals pentru teste; nu este fallback pentru Outlook real."""

import copy
from datetime import datetime
import threading


class FakeMailBackend:
    def __init__(self, messages=None, folders=None):
        self.messages = messages or []
        self.folders = folders or [{"store_id": "store", "folder_id": "inbox", "mailbox": "Test", "path": "Inbox"}]
        self.available = True
        self.calls = []
        self.block = None

    def _check(self, operation):
        self.calls.append((operation, threading.get_ident()))
        if self.block:
            self.block.wait(5)
        if not self.available:
            raise RuntimeError("Outlook Classic indisponibil (backend fals).")

    def list_mail_folders(self):
        self._check("folders")
        return copy.deepcopy(self.folders)

    def scan_mail_page(self, plan):
        self._check("page")
        initial = plan["phase"] == "initial"
        key = "received_at" if initial else "modified_at"
        lower, upper = datetime.fromisoformat(plan["from"]), datetime.fromisoformat(plan["to"])
        candidates = [m for m in self.messages if m["header"]["store_id"] == plan["store_id"] and
            m["header"]["folder_id"] == plan["folder_id"] and lower <= datetime.fromisoformat(m["header"][key]) < upper]
        candidates.sort(key=lambda m: (m["header"][key], m["header"]["entry_id"]), reverse=initial)
        rows = candidates[plan["offset"]:plan["offset"] + plan["limit"]]
        return {"headers": [copy.deepcopy(m["header"]) for m in rows], "next_offset": plan["offset"] + len(rows),
                "done": plan["offset"] + len(rows) >= len(candidates), "consumed": len(rows)}

    def read_mail_details(self, locators):
        self._check("details")
        out = []
        for locator in locators:
            message = next(m for m in self.messages if m["header"]["store_id"] == locator["store_id"] and m["header"]["entry_id"] == locator["entry_id"])
            out.append({k: copy.deepcopy(v) for k, v in message.items() if k != "unread"})
        return out
