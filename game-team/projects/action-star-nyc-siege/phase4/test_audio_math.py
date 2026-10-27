"""Audio math QA — Phase 4. No Ursina, no audio device needed.

Proves, numerically:
  1. Every shipped WAV (10 assets + 10 Bullet-Time variants) decodes as
     mono 16-bit PCM at the project sample rate, with a sane duration.
  2. Every variant's duration is ~2.5x its source (0.4x speed).
  3. The pitch shift is real: a known 440 Hz tone resampled at 0.4x
     measures ~176 Hz by FFT (0.4 x 440) and lasts ~2.5x as long.

Run:  python test_audio_math.py     (exit 0 = all checks passed)
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase4.generate_audio_assets import SAMPLE_RATE, resample_rate  # noqa: E402

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
BT = ASSETS / "bullet_time"

# (filename, min_s, max_s) sane duration windows for the normal-speed files.
EXPECTED = {
    "bgm_loop.wav": (7.5, 8.5),
    "sfx_gunshot.wav": (0.15, 0.45),
    "sfx_casing.wav": (0.10, 0.40),
    "sfx_slide.wav": (0.40, 0.90),
    "sfx_glass_break.wav": (0.45, 0.95),
    "sfx_melee_hit.wav": (0.10, 0.40),
    "sfx_server_explosion.wav": (0.80, 1.40),
    "ui_charge.wav": (0.15, 0.45),
    "ui_combo.wav": (0.08, 0.30),
    "ui_rank.wav": (0.60, 1.20),
}

failures = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}")
    if not ok:
        failures.append(label)


def decode(path: Path):
    with wave.open(str(path), "rb") as wf:
        params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate(),
                  wf.getnframes())
        frames = wf.readframes(params[3])
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
    return params, samples


def dominant_freq(samples: np.ndarray, rate: int) -> float:
    windowed = samples * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / rate)
    return float(freqs[int(np.argmax(spectrum))])


def main() -> int:
    for name, (lo, hi) in EXPECTED.items():
        for folder, tag in ((ASSETS, "normal"), (BT, "bullet_time")):
            path = folder / name
            if not path.exists():
                check(False, f"{tag}/{name}", "MISSING FILE")
                continue
            (ch, width, rate, nframes), samples = decode(path)
            dur = nframes / rate
            expect_dur = (lo, hi) if tag == "normal" else (lo * 2.5, hi * 2.5)
            ok = (ch == 1 and width == 2 and rate == SAMPLE_RATE
                  and expect_dur[0] <= dur <= expect_dur[1]
                  and np.max(np.abs(samples)) > 0.05)
            check(ok, f"{tag}/{name}",
                  f"ch={ch} width={width} rate={rate} dur={dur:.2f}s "
                  f"peak={np.max(np.abs(samples)):.2f}")

    # Duration ratio per asset: variant / source ~= 2.5 (0.4x speed).
    for name in EXPECTED:
        (_, _, _, n_src), _ = decode(ASSETS / name)
        (_, _, _, n_var), _ = decode(BT / name)
        ratio = n_var / n_src
        check(abs(ratio - 2.5) < 0.02, f"ratio {name}", f"{ratio:.3f}x")

    # FFT pitch proof on a known tone.
    tone_t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    tone = 0.7 * np.sin(2 * np.pi * 440.0 * tone_t)
    shifted = resample_rate(tone, 0.4)
    f_src = dominant_freq(tone, SAMPLE_RATE)
    f_dst = dominant_freq(shifted, SAMPLE_RATE)
    check(abs(f_src - 440.0) < 2.0, "FFT source tone", f"{f_src:.1f} Hz")
    check(abs(f_dst - 176.0) < 4.0, "FFT shifted tone (0.4x)",
          f"{f_dst:.1f} Hz (expect ~176)")
    check(abs(len(shifted) / len(tone) - 2.5) < 0.01, "shifted duration",
          f"{len(shifted) / SAMPLE_RATE:.2f}s vs 1.00s")

    print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
