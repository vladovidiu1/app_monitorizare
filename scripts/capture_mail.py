"""Capture the real mail UI on disposable data, without calling Outlook or sending messages."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    from PIL import ImageGrab  # Optional screenshot helper, not an application dependency.
    from focusdesk.domain.models import Kind
    from focusdesk.integrations.outlook import MailHandoffUncertain
    from focusdesk.ui.app import FocusDeskApp
    from focusdesk.ui.common import apply_theme
    from focusdesk.ui.design import MIN_WINDOW, px
    from focusdesk.ui.file_picker import TaskFilePicker
    from focusdesk.ui.mail_ui import MailDialog

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/mail"))
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = {"platform": sys.platform, "scale_simulated": args.scale, "outlook_real": False,
               "windows_dpi_verified": False, "captures": [], "geometry_checks": []}
    with tempfile.TemporaryDirectory(prefix="focusdesk-mail-demo-") as temporary:
        base = Path(temporary)
        os.environ["APPDATA"] = str(base / "config")
        app = FocusDeskApp()
        app.root.tk.call("tk", "scaling", args.scale * 96 / 72)
        apply_theme(app.root)
        app.root.minsize(*(px(app.root, value) for value in MIN_WINDOW))
        app.root.geometry(f"{px(app.root,1100)}x{px(app.root,700)}+0+0")
        errors = []
        app.root.report_callback_exception = lambda cls, error, tb: errors.append(f"{cls.__name__}: {error}")
        assert app.open_workspace(base / "workspace", create=True)
        project = app.ws.create_node(Kind.PROJECT, "Raportări lunare")
        node = app.ws.create_node(Kind.TASK, "Verifică raportul și cere clarificări asupra regulilor de calcul", project.id,
            description="Scop\nVerificarea tuturor valorilor.\n\n" + "Pasul 1\n    Păstrează diacriticele și indentarea.\n" * 20)
        folder = app.files.files_dir(project.id)
        folder.mkdir(exist_ok=True)
        first = folder / "Raport.txt"
        first.write_text("Document demonstrativ\n" * 40, encoding="utf-8")
        external = base / "referință"
        external.mkdir()
        second = external / "Raport.txt"
        second.write_text("Note demonstrative\n" * 20, encoding="utf-8")
        app.select_node(node.id, reveal=True)

        def pump():
            for _ in range(8):
                app.root.update()
                time.sleep(.02)

        def capture(name, window):
            pump()
            window.lift()
            pump()
            box = (window.winfo_rootx(), window.winfo_rooty(),
                   window.winfo_rootx() + window.winfo_width(), window.winfo_rooty() + window.winfo_height())
            ImageGrab.grab(bbox=box).save(args.output / (name + ".png"))
            results["captures"].append(name + ".png")

        def visible(name, widget, window):
            x, y = widget.winfo_rootx() - window.winfo_rootx(), widget.winfo_rooty() - window.winfo_rooty()
            valid = (widget.winfo_ismapped() and x >= 0 and y >= 0 and x + widget.winfo_width() <= window.winfo_width()
                     and y + widget.winfo_height() <= window.winfo_height())
            results["geometry_checks"].append({"name": name, "ok": bool(valid)})
            assert valid, name

        dialog = None
        try:
            dialog = MailDialog(app.root, app, node)
            pump()  # Let design.py apply its first-map scaling before explicit geometry checks.
            dialog.geometry(f"{px(dialog,860)}x{px(dialog,730)}+10+10")
            dialog.to_var.set("ana@firma.ro")
            dialog.cc_var.set("ion@firma.ro")
            dialog._select_attachments([first, second])
            capture("email-atasamente", dialog)
            for name in ("ok_btn", "draft_btn", "attachment_tree"):
                visible("normal-" + name, getattr(dialog, name), dialog)
            picker = TaskFilePicker(dialog, app.files, node.id)
            picker.location.current(next(i for i, loc in enumerate(picker.locations) if loc.path == folder))
            picker._select_location()
            capture("email-fisiere-proiect", picker)
            picker.destroy()
            dialog.geometry(f"{px(dialog,680)}x{px(dialog,540)}+10+10")
            dialog._failed(dialog._build(), MailHandoffUncertain("Exemplu demonstrativ: Outlook nu a răspuns la timp."))
            capture("email-eroare-minim", dialog)
            for name in ("ok_btn", "draft_btn", "checked_btn", "feedback"):
                visible("minim-" + name, getattr(dialog, name), dialog)
            dialog.form.canvas.yview_moveto(1)
            pump()
            visible("minim-atasamente-derulate", dialog.attachment_count, dialog)
            assert not errors, errors
        finally:
            if dialog is not None and dialog.winfo_exists():
                dialog.destroy()
            app.inspector.revert()
            app.on_close()
    (args.output / "manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
