"""Genereaza pictograma aplicatiei (resources/focusdesk.ico) cu Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "focusdesk" / "resources" / "focusdesk.ico"


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size // 5
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=(37, 99, 235, 255))
    # bifa alba (task finalizat) + cerc de focus
    w = max(2, size // 12)
    cx, cy, rad = size / 2, size / 2, size * 0.33
    d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), outline=(255, 255, 255, 255), width=w)
    d.line([(size * 0.36, size * 0.52), (size * 0.46, size * 0.62), (size * 0.66, size * 0.40)],
           fill=(255, 255, 255, 255), width=w, joint="curve")
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    base = draw(256)
    base.save(OUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("scris", OUT)


if __name__ == "__main__":
    main()
