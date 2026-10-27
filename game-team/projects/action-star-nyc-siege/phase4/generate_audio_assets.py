"""Synthesized v1 audio assets for Action Star: NYC Siege 3D.

NO licensed audio exists for this project, so every sound the game ships
in v1 is generated here with numpy — genuine, decodable 16-bit PCM WAV
files (mood-synth BGM loop, synthesized SFX, UI cues). They are honestly
labelled "synthesized v1" and are meant to be replaced by recorded or
licensed assets later; the file names and the SoundManager API stay the
same when that happens.

For every asset this script also renders the Bullet-Time variant at
0.4x playback speed into ``assets/bullet_time/`` (resampled: same
samples played over 2.5x the duration, so pitch drops to 0.4x — the
mechanism SoundManager crossfades to while Bullet Time is active).

Run:  python generate_audio_assets.py
Outputs land next to this script in ./assets/ and ./assets/bullet_time/.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
BULLET_TIME_RATE = 0.4          # pitch/speed factor while Bullet Time is on
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
BT_DIR = ASSETS / "bullet_time"


def _env(n: int, attack: float = 0.01, decay_power: float = 1.0) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    env = np.minimum(1.0, t / max(attack, 1e-4)) * (1.0 - t) ** decay_power
    return env


def _write_wav(path: Path, samples: np.ndarray) -> None:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


def resample_rate(samples: np.ndarray, rate: float) -> np.ndarray:
    """Play ``samples`` back at ``rate`` speed (pitch scales with rate)."""
    if rate <= 0:
        raise ValueError("rate must be > 0")
    n_out = int(round(len(samples) / rate))
    src = np.arange(len(samples), dtype=np.float64)
    dst = np.linspace(0.0, len(samples) - 1, n_out)
    return np.interp(dst, src, samples).astype(np.float64)


# ---------------------------------------------------------------------------
# Asset synthesizers (each returns a mono float array at SAMPLE_RATE)
# ---------------------------------------------------------------------------
def synth_bgm_loop() -> np.ndarray:
    """Moody 8 s synth loop: dark minor pad + low pulse, click-free wrap."""
    dur = 8.0
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    # Two detuned saws through a slow tremolo read as a synth pad.
    def saw(freq: float) -> np.ndarray:
        return 2.0 * ((t * freq) % 1.0) - 1.0
    pad = 0.20 * saw(110.0) + 0.16 * saw(110.7) + 0.14 * saw(165.0)
    pad *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.25 * t)
    # Low heartbeat pulse on beats 0 and 2 of each 2 s bar.
    pulse = np.zeros(n)
    for start in (0.0, 2.0, 4.0, 6.0):
        idx = int(start * SAMPLE_RATE)
        seg = np.arange(int(0.45 * SAMPLE_RATE)) / SAMPLE_RATE
        pulse[idx:idx + len(seg)] += 0.5 * np.sin(2 * np.pi * 55.0 * seg) \
            * np.exp(-seg * 7.0)
    out = pad * 0.55 + pulse
    # Crossfade the tail into the head so the loop wraps without a click.
    fade = int(0.25 * SAMPLE_RATE)
    head = out[:fade].copy()
    out[:fade] = out[:fade] * np.linspace(0.3, 1.0, fade) \
        + out[-fade:] * np.linspace(0.7, 0.0, fade)
    _ = head
    return out * 0.8


def synth_gunshot() -> np.ndarray:
    rng = np.random.default_rng(11)
    dur = 0.28
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    noise = rng.standard_normal(n) * np.exp(-t * 22.0)
    crack = 0.9 * np.sin(2 * np.pi * 180.0 * t) * np.exp(-t * 30.0)
    body = 0.5 * np.sin(2 * np.pi * 70.0 * t) * np.exp(-t * 12.0)
    return (noise * 0.8 + crack + body) * 0.9


def synth_casing() -> np.ndarray:
    """Shell casing tick: two tiny metallic pings on a hard floor."""
    rng = np.random.default_rng(23)
    dur = 0.22
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    out = np.zeros(n)
    for start, freq, amp in ((0.0, 4200.0, 0.55), (0.09, 3600.0, 0.35),
                             (0.16, 3900.0, 0.2)):
        seg_t = t - start
        mask = seg_t >= 0
        out[mask] += amp * np.sin(2 * np.pi * freq * seg_t[mask]) \
            * np.exp(-seg_t[mask] * 90.0)
    out += rng.standard_normal(n) * 0.03 * np.exp(-t * 60.0)
    return out


def synth_slide() -> np.ndarray:
    rng = np.random.default_rng(37)
    dur = 0.65
    n = int(SAMPLE_RATE * dur)
    noise = rng.standard_normal(n)
    # Crude low-pass via cumulative smoothing = fabric-on-floor friction.
    kernel = np.ones(24) / 24.0
    smooth = np.convolve(noise, kernel, mode="same")
    return smooth * _env(n, attack=0.08, decay_power=0.6) * 2.2


def synth_glass_break() -> np.ndarray:
    rng = np.random.default_rng(41)
    dur = 0.7
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    out = rng.standard_normal(n) * 0.25 * np.exp(-t * 9.0)
    for freq in (2900.0, 3400.0, 4100.0, 4700.0, 5300.0):
        start = rng.uniform(0.0, 0.12)
        seg_t = t - start
        mask = seg_t >= 0
        out[mask] += 0.22 * np.sin(2 * np.pi * freq * seg_t[mask]) \
            * np.exp(-seg_t[mask] * rng.uniform(14.0, 26.0))
    return out


def synth_melee_hit() -> np.ndarray:
    rng = np.random.default_rng(53)
    dur = 0.22
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    thump = 0.95 * np.sin(2 * np.pi * 95.0 * t) * np.exp(-t * 26.0)
    smack = rng.standard_normal(n) * 0.4 * np.exp(-t * 40.0)
    return thump + smack


def synth_server_explosion() -> np.ndarray:
    """Electrical explosion: noise burst, falling zap sweep, low boom."""
    rng = np.random.default_rng(67)
    dur = 1.1
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    noise = rng.standard_normal(n) * 0.8 * np.exp(-t * 5.5)
    zap_freq = 2400.0 * np.exp(-t * 4.0) + 120.0
    zap = 0.4 * np.sin(2 * np.pi * np.cumsum(zap_freq) / SAMPLE_RATE) \
        * np.exp(-t * 6.0)
    boom = 0.7 * np.sin(2 * np.pi * 50.0 * t) * np.exp(-t * 3.5)
    crackle = (rng.standard_normal(n) > 2.2) * 0.5 * np.exp(-t * 3.0)
    return noise + zap + boom + crackle


def _blip(freq_start: float, freq_end: float, dur: float,
          seed: int) -> np.ndarray:
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    freqs = np.linspace(freq_start, freq_end, n)
    tone = np.sin(2 * np.pi * np.cumsum(freqs) / SAMPLE_RATE)
    return tone * _env(n, attack=0.02, decay_power=0.8) * 0.6


def synth_ui_charge() -> np.ndarray:
    """Bullet-Time charge-ready beep: bright rising two-step blip."""
    a = _blip(880.0, 880.0, 0.09, 71)
    b = _blip(1318.0, 1318.0, 0.14, 72)
    return np.concatenate([a, np.zeros(int(0.03 * SAMPLE_RATE)), b])


def synth_ui_combo() -> np.ndarray:
    """Combo registration blip: quick upward chirp."""
    return _blip(660.0, 1320.0, 0.12, 83)


def synth_ui_rank() -> np.ndarray:
    """Rank-announcement sting: three-note brass-ish fanfare hit."""
    n = int(SAMPLE_RATE * 0.9)
    t = np.arange(n) / SAMPLE_RATE
    out = np.zeros(n)
    for start, freq in ((0.0, 392.0), (0.14, 523.0), (0.28, 784.0)):
        seg_t = t - start
        mask = seg_t >= 0
        out[mask] += 0.4 * np.sin(2 * np.pi * freq * seg_t[mask]) \
            * np.exp(-seg_t[mask] * 3.2)
        out[mask] += 0.2 * np.sin(4 * np.pi * freq * seg_t[mask]) \
            * np.exp(-seg_t[mask] * 4.5)
    return out * _env(n, attack=0.005, decay_power=0.4)


ASSET_BUILDERS = {
    "bgm_loop.wav": synth_bgm_loop,
    "sfx_gunshot.wav": synth_gunshot,
    "sfx_casing.wav": synth_casing,
    "sfx_slide.wav": synth_slide,
    "sfx_glass_break.wav": synth_glass_break,
    "sfx_melee_hit.wav": synth_melee_hit,
    "sfx_server_explosion.wav": synth_server_explosion,
    "ui_charge.wav": synth_ui_charge,
    "ui_combo.wav": synth_ui_combo,
    "ui_rank.wav": synth_ui_rank,
}


def main() -> None:
    manifest = {"sample_rate": SAMPLE_RATE,
                "bullet_time_rate": BULLET_TIME_RATE, "assets": {}}
    for name, builder in ASSET_BUILDERS.items():
        samples = builder()
        _write_wav(ASSETS / name, samples)
        shifted = resample_rate(samples, BULLET_TIME_RATE)
        _write_wav(BT_DIR / name, shifted)
        manifest["assets"][name] = {
            "duration_s": round(len(samples) / SAMPLE_RATE, 3),
            "bullet_time_duration_s": round(len(shifted) / SAMPLE_RATE, 3),
            "origin": "synthesized v1 (numpy) — no licensed audio",
        }
        print(f"WROTE assets/{name} ({len(samples) / SAMPLE_RATE:.2f}s) "
              f"+ bullet_time variant ({len(shifted) / SAMPLE_RATE:.2f}s)")
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("WROTE assets/manifest.json")


if __name__ == "__main__":
    main()
