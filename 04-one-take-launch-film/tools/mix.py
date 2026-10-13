"""Mix the 27-second music edit with the Mixkit sound effects and loudness-normalise to -14 LUFS.

Every effect is placed so that its measured peak (loudest 10 ms window) lands on its cue time, at a
level set against the music under that cue (so a click is as audible in the drop as in the breakdown,
within limits).
Cues come from the film itself (window.SFX, dumped by render.mjs to sfx-cues.json).

Usage: python tools/mix.py [cues.json] [out.wav]
Needs numpy, soundfile and ffmpeg.
"""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent.parent
SR, LEN = 48000, 27.0
MUSIC = HERE / "assets/music/music-27s.wav"
SFX_DIR = HERE / "assets/sfx"
REL_DB = {    # effect level relative to the music around its cue (RMS over ±50 ms of the peak)
    "click": -6, "pop": -5, "rise": -7, "shutter": -4, "paper": -7, "slide": -7, "whoosh": -5,
    "glass": -8, "glassy": -6, "liquid": -5, "tap": -5, "tick": -7, "bubble": -6, "swell": -6,
    "suck": -6, "stretch": -6, "blind": -6, "lift": -7, "page": -7, "thunk": -6, "scroll": -8,
    "check": -4, "printer": -6, "van": -5, "ding": -4, "boom": 0, "impact": -2,
}


def load(path):
    """Decode anything ffmpeg reads to float32 stereo at SR."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def peak_time(x):
    """Centre of the loudest 10 ms window."""
    mono = np.abs(x).mean(axis=1)
    win = int(0.01 * SR)
    env = np.convolve(mono ** 2, np.ones(win) / win, mode="same")
    return int(np.argmax(env))


def main(cues_path="sfx-cues.json", out="mix.wav"):
    cues = json.load(open(HERE / cues_path))
    n = int(LEN * SR)
    music = load(MUSIC)[:n]
    mono = music.mean(axis=1)
    w = int(0.05 * SR)
    rms = lambda x: float(np.sqrt((x ** 2).mean()) + 1e-9)
    floor = rms(mono) * 0.35          # quiet passages do not push effects up without limit
    bus = np.zeros((n, 2), dtype=np.float64)
    files = {p.stem.split("-")[0]: p for p in SFX_DIR.glob("*.wav")}
    cache, report = {}, []
    for t, name in cues:
        if name not in cache:
            x = load(files[name])
            pk = peak_time(x)
            cache[name] = (x, pk, rms(x.mean(axis=1)[max(0, pk - w):pk + w]))
        x, pk, x_rms = cache[name]
        i = int(round(t * SR))
        m_rms = max(rms(mono[max(0, i - w):i + w]), floor)
        g = m_rms * 10 ** (REL_DB[name] / 20) / x_rms
        start = i - pk
        a, b = max(0, start), min(n, start + len(x))
        if b > a:
            bus[a:b] += x[a - start:b - start] * g
        report.append((round(t, 3), name, round(pk / SR, 3), round(20 * np.log10(g), 1)))
    bus[:len(music)] += music
    tmp = HERE / "assets/mix-raw.wav"
    sf.write(tmp, bus.astype(np.float32), SR, subtype="FLOAT")
    # two-pass loudnorm: measure, then apply linearly
    meas = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(tmp), "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", meas, re.S).group(0))
    af = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          "alimiter=limit=0.83:attack=2:release=40:level=false")   # keeps true peaks under -1 dBFS
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-af", af, "-ar", str(SR), str(HERE / out)], check=True)
    chk = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(HERE / out), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", chk)[-1]
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", chk)[-1]
    print(f"{out}: {len(cues)} cues, integrated {lufs} LUFS, true peak {tp} dBFS")
    json.dump(report, open(HERE / "assets/mix-report.json", "w"))


if __name__ == "__main__":
    main(*sys.argv[1:3])
