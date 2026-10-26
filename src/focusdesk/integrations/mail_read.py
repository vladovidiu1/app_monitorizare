"""Citire COM strict read-only. Toate valorile returnate sunt JSON serializabile."""

from datetime import datetime, timezone
import json
import re

UTC = timezone.utc
PROPS = "http://schemas.microsoft.com/mapi/proptag/"


def prop(item, code, default=None):
    try:
        return item.PropertyAccessor.GetProperty(PROPS + code)
    except Exception:
        return default


def smtp_address(item):
    """PR_SENDER_SMTP_ADDRESS, apoi AddressEntry/ExchangeUser/DL; niciodată display-name guessing."""
    candidates = [prop(item, "0x5D01001F"), prop(item, "0x5D01001E")]
    try:
        if item.SenderEmailType == "EX":
            sender = item.Sender
            for method in ("GetExchangeUser", "GetExchangeDistributionList"):
                try:
                    entity = getattr(sender, method)()
                    candidates.append(entity.PrimarySmtpAddress if entity is not None else None)
                except Exception:
                    pass
            candidates.extend([prop(sender, "0x39FE001F"), prop(sender, "0x39FE001E")])
        else:
            candidates.append(item.SenderEmailAddress)
    except Exception:
        pass
    return next((str(value).strip() for value in candidates if value and re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", str(value).strip())), None)


def utc_property(item, code, fallback):
    value = prop(item, code)
    if value is not None:
        # PropertyAccessor PT_SYSTIME is UTC, even if pywin32 labels its wall clock incorrectly.
        return value.replace(tzinfo=UTC).isoformat()
    from .outlook_com import to_utc
    return to_utc(fallback).isoformat()


def namespace(backend):
    import win32com.client
    # Monitoring never launches Outlook; sending/calendar keep their existing connection policy.
    app = win32com.client.GetActiveObject("Outlook.Application")
    ns = app.GetNamespace("MAPI")
    if bool(getattr(ns, "Offline", False)):
        raise RuntimeError("Outlook Classic este offline.")
    return ns


def header(item, store_id, folder_id):
    key = prop(item, "0x300B0102", b"")
    if isinstance(key, (bytes, bytearray, list, tuple)):
        key = bytes(key).hex()
    return {"store_id": store_id, "folder_id": folder_id, "entry_id": str(item.EntryID),
        "internet_id": str(prop(item, "0x1035001F", "") or prop(item, "0x1035001E", "") or ""), "search_key": str(key or ""),
        "conversation_id": str(getattr(item, "ConversationID", "") or ""), "subject": str(item.Subject or "")[:500],
        "sender_name": str(getattr(item, "SenderName", "") or "")[:200], "sender_smtp": smtp_address(item),
        "sent_at": utc_property(item, "0x00390040", item.SentOn),
        "received_at": utc_property(item, "0x0E060040", item.ReceivedTime),
        "modified_at": utc_property(item, "0x30080040", item.LastModificationTime)}


def list_folders(backend):
    try:
        ns = namespace(backend)
        result = []
        for number, store in enumerate(ns.Stores):
            if number >= 30:
                break
            stack = [(store.GetRootFolder(), 0)]
            while stack and len(result) < 300:
                folder, depth = stack.pop()
                if int(folder.DefaultItemType) == 0:
                    result.append({"store_id": str(store.StoreID), "mailbox": str(store.DisplayName),
                                   "folder_id": str(folder.EntryID), "path": str(folder.FolderPath)})
                if depth < 8:
                    stack.extend((child, depth + 1) for child in folder.Folders)
        return result
    except Exception:
        raise RuntimeError("Foldere indisponibile. Deschide Outlook Classic cu profilul conectat; New Outlook nu suportă COM.") from None


def scan_page(backend, plan):
    try:
        if not 1 <= plan["limit"] <= 50 or not 0 <= plan["offset"] <= 10000:
            raise ValueError("Paginare peste limita acceptată.")
        ns = namespace(backend)
        folder = ns.GetFolderFromID(plan["folder_id"], plan["store_id"])
        property_code = "0x0E060040" if plan["phase"] == "initial" else "0x30080040"
        start = datetime.fromisoformat(plan["from"]).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        end = datetime.fromisoformat(plan["to"]).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        query = f'@SQL="{PROPS + property_code}" >= \'{start}\' AND "{PROPS + property_code}" < \'{end}\''
        table = folder.GetTable(query)
        table.Sort("ReceivedTime" if plan["phase"] == "initial" else "LastModificationTime", plan["phase"] == "initial")
        if plan["offset"]:
            table.GetArray(plan["offset"])  # bounded metadata skip, never a body read
        out, consumed = [], 0
        while not table.EndOfTable and consumed < plan["limit"]:
            row = table.GetNextRow()
            consumed += 1
            if not str(row.Item("MessageClass")).startswith("IPM.Note"):
                continue
            item = ns.GetItemFromID(str(row.Item("EntryID")), plan["store_id"])
            if int(item.Class) == 43:
                out.append(header(item, plan["store_id"], plan["folder_id"]))
        result = {"headers": out, "next_offset": plan["offset"] + consumed, "done": bool(table.EndOfTable), "consumed": consumed}
        json.dumps(result)  # assert the COM boundary contains no proxy/datetime objects
        return result
    except Exception:
        raise RuntimeError("Citire mailuri indisponibilă sau paginare invalidă. Checkpoint-ul nu a avansat; verifică Outlook Classic/conexiunea.") from None


def read_details(backend, locators):
    try:
        if len(locators) > 50:
            raise ValueError("Lot prea mare.")
        ns = namespace(backend)
        result = []
        for locator in locators:
            item = ns.GetItemFromID(locator["entry_id"], locator["store_id"])
            if int(item.Class) != 43:
                raise ValueError("Elementul nu este MailItem.")
            body = str(item.Body or "")
            attachments = []
            for index in range(1, min(int(item.Attachments.Count), 20) + 1):
                attachment = item.Attachments.Item(index)
                attachments.append({"filename": str(attachment.FileName)[:255], "size": int(attachment.Size), "type": int(attachment.Type)})
            result.append({"header": header(item, locator["store_id"], str(item.Parent.EntryID)),
                "body": body[:12000], "body_truncated": len(body) > 12000, "attachments": attachments})
        json.dumps(result)
        return result
    except Exception:
        raise RuntimeError("Detaliile mailului nu pot fi citite. Poate fi mutat sau Outlook este indisponibil; reîncearcă scanarea.") from None
