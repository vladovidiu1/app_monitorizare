"""Smoke UI: porneste aplicatia pe un workspace demo temporar si salveaza o captura de ecran."""

from __future__ import annotations

import sys
import tempfile
import time
import faulthandler
from datetime import datetime, timedelta, timezone
from pathlib import Path

faulthandler.dump_traceback_later(25, exit=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402

from focusdesk.services.demo import create_demo_workspace  # noqa: E402
from focusdesk.services.sessions import SessionService  # noqa: E402
from focusdesk.services.workspace import Workspace  # noqa: E402
from focusdesk.ui import common  # noqa: E402
from focusdesk.ui.app import FocusDeskApp  # noqa: E402

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "focusdesk_smoke.png"
mode = sys.argv[2] if len(sys.argv) > 2 else "today"
if len(sys.argv) > 3:  # al treilea argument: tema ttkbootstrap pentru modul deschis, pentru comparatii de aspect
    common.THEMES["light"] = sys.argv[3]
if len(sys.argv) > 4:
    common.THEMES["dark"] = sys.argv[4]
tmp = Path(tempfile.mkdtemp(prefix="fd_smoke_")) / "demo"
create_demo_workspace(tmp)

ws0 = Workspace.open(tmp)
_t = next(n for n in ws0.nodes.values() if n.title == "Verificare diferențe XML")
_svc = SessionService(ws0)
_base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
_svc.create(_t.id, _base, _base + timedelta(hours=1), note="Prima parte")
_svc.create(_t.id, _base + timedelta(days=1), _base + timedelta(days=1, hours=2), reserve_calendar=True)
ws0.close()

if mode == "darkstart":  # porneste direct in tema intunecata (nu prin comutare)
    from focusdesk.config import AppConfig  # noqa: E402

    _load = AppConfig.load
    AppConfig.load = classmethod(lambda cls: _load().model_copy(update={"theme": "dark"}))

app = FocusDeskApp(tmp)


def capture_window(hwnd: int) -> Image.Image:
    """PrintWindow: capteaza doar fereastra aplicatiei, chiar daca ecranul este blocat sau acoperit."""
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    info = BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(info), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def shoot() -> None:
    app.root.update_idletasks()
    app.root.update()
    time.sleep(0.6)
    app.root.update()
    target = _dialog[0] if _dialog else app.root
    capture_window(int(target.frame(), 16)).save(out)
    print("saved", out)
    if _dialog:
        _dialog[0].destroy()
    app.on_close()


_dialog: list = []


def prepare() -> None:
    ws = app.ws
    task = next(n for n in ws.nodes.values() if n.title == "Verificare diferențe XML")
    if mode == "mail":
        from focusdesk.ui.mail_ui import MailDialog

        app.select_node(task.id, reveal=True)
        dlg = MailDialog(app.root, app, task)
        dlg.to_var.set("ana.popescu@firma.ro")
        _dialog.append(dlg)
    elif mode == "tree":
        app.select_node(task.id, reveal=True)
    elif mode in ("proj", "darkstart"):
        app.show_node_scope(next(n for n in ws.nodes.values() if n.title == "Validări XML").id)
    elif mode == "dark":
        app.dark_var.set(True)
        app.toggle_theme()
    elif mode == "calendar":
        app.show_view("calendar", select_sidebar=True)
    elif mode.startswith("tab:"):
        app.select_node(task.id, reveal=True)
        app.inspector.show_tab(mode[4:])
    app.root.after(900, shoot)


app.root.after(2000, prepare)
app.config.save = lambda: None  # nu scrie in config-ul real
app.run()
