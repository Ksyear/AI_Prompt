"""Checks on the rendered film.

1. One frame per beat (taken mid-beat) laid out as a contact sheet.
2. Single-frame pops: d[k] = mean |frame k - frame k-1|; a pop is a frame whose difference is more than
   three times both neighbours' differences (and big enough to see).

Usage: python tools/check.py [film.mp4] [beats.jpg]
Needs numpy, Pillow and ffmpeg.
"""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
FPS, BEAT, S = 60, 0.5, 240          # analysis size S×S


def frames(path, size):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={size}:{size}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = size * size * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(size, size, 3)


def main(film="film.mp4", sheet="beats.jpg"):
    film = HERE / film
    diffs, keep, prev, first, last = [], {}, None, None, None
    beat_frames = {int(round((n * BEAT + BEAT / 2) * FPS)): n + 1 for n in range(54)}
    for k, f in enumerate(frames(film, S)):
        if first is None:
            first = f.astype(np.float32)
        last = f.astype(np.float32)
        g = last.mean(axis=2)
        diffs.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
        if k in beat_frames:
            keep[beat_frames[k]] = f
    d = np.array(diffs)
    pops = [k for k in range(2, len(d) - 1) if d[k] > 1.0 and d[k] > 3 * d[k - 1] and d[k] > 3 * d[k + 1]]
    print(f"{len(d)} frames; mean diff {d.mean():.2f}; max {d.max():.2f} at frame {int(d.argmax())} ({d.argmax() / FPS:.2f} s)")
    print(f"single-frame pops (> 3x both neighbours): {len(pops)}")
    for k in pops:
        print(f"  frame {k} ({k / FPS:.3f} s): {d[k]:.2f} vs {d[k - 1]:.2f} / {d[k + 1]:.2f}")
    print(f"first vs last frame mean |diff|: {np.abs(first - last).mean():.2f} (0-255)")
    T, cols = 220, 9
    rows = (len(keep) + cols - 1) // cols
    out = Image.new("RGB", (cols * (T + 4) + 4, rows * (T + 20) + 4), (30, 30, 30))
    dr = ImageDraw.Draw(out)
    for i, n in enumerate(sorted(keep)):
        x, y = 4 + (i % cols) * (T + 4), 4 + (i // cols) * (T + 20)
        out.paste(Image.fromarray(keep[n]).resize((T, T)), (x, y + 16))
        dr.text((x, y + 2), f"beat {n}", fill=(255, 255, 255))
    out.save(HERE / sheet, quality=86)
    np.save(HERE / "assets/frame-diffs.npy", d)


if __name__ == "__main__":
    main(*sys.argv[1:3])
