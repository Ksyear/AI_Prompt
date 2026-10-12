"""Compose nine separately generated panels into one 9:16 contact sheet.

Every panel is centre-cropped to exactly 9:16, laid out 3x3 on black with
rounded corners, and gets the same white rounded label box with black
sans-serif text, so the grid ratios and label spelling are exact.

Usage: python compose.py [panels_dir] [output.png]
Needs Pillow.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

LABELS = ["/wormseye:", "/extremecloseup:", "/droneview:", "/profile:", "/topdown:",
          "/lowthreequarter:", "/widefull:", "/overshoulder:", "/highangle:"]
W, H = 2160, 3840            # 9:16 canvas
GAP = 24                     # black border between and around panels
PW = (W - 4 * GAP) // 3      # 688
PH = round(PW * 16 / 9)      # 1223
TOP = (H - (3 * PH + 2 * GAP)) // 2
RADIUS = 26
SS = 4                       # supersampling for smooth rounded edges
FONTS = [("/System/Library/Fonts/HelveticaNeue.ttc", 10),   # Helvetica Neue Medium (macOS)
         ("/System/Library/Fonts/Helvetica.ttc", 0), ("/Library/Fonts/Arial.ttf", 0), ("DejaVuSans.ttf", 0)]


def rounded_mask(size, radius):
    w, h = size
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius * SS, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def crop_9x16(img):
    w, h = img.size
    if w / h > 9 / 16:                 # too wide: trim the sides
        nw = round(h * 9 / 16)
        x = (w - nw) // 2
        return img.crop((x, 0, x + nw, h))
    nh = round(w * 16 / 9)             # too tall: trim top and bottom evenly
    y = (h - nh) // 2
    return img.crop((0, y, w, y + nh))


def load_font(px):
    for path, index in FONTS:
        try:
            return ImageFont.truetype(path, px, index=index)
        except OSError:
            continue
    return ImageFont.load_default(px)


def label_box(text):
    bw, bh = round(PW * 0.86), round(PH * 0.085)
    box = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    box.paste((255, 255, 255, 255), (0, 0), rounded_mask((bw, bh), RADIUS))
    font = load_font(round(bh * 0.42))
    d = ImageDraw.Draw(box)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    d.text(((bw - (r - l)) / 2 - l, (bh - (b - t)) / 2 - t), text, font=font, fill=(0, 0, 0, 255))
    return box


def main(panels_dir="panels", out="contact-sheet-9shot.png"):
    sheet = Image.new("RGB", (W, H), (0, 0, 0))
    mask = rounded_mask((PW, PH), RADIUS)
    for i, text in enumerate(LABELS):
        src = Image.open(Path(panels_dir) / f"panel-{i + 1:02d}.png").convert("RGB")
        panel = crop_9x16(src).resize((PW, PH), Image.LANCZOS)
        box = label_box(text)
        panel.paste(box, ((PW - box.width) // 2, PH - box.height - round(PH * 0.03)), box)
        col, row = i % 3, i // 3
        sheet.paste(panel, (GAP + col * (PW + GAP), TOP + row * (PH + GAP)), mask)
    sheet.save(out)
    print(f"{out}: {W}x{H}, panels {PW}x{PH}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
