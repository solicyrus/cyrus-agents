"""SoundManager — dynamic audio for Action Star: NYC Siege 3D.

Channels: BGM (one looping track), SFX (fire-and-forget one-shots),
UI (menu/feedback cues via :meth:`SoundManager.play_ui`). Per-channel
volumes are independent; SFX/UI honour the channel volume at play time.

Bullet-Time PITCH SHIFT — mechanism (chosen, documented honestly):
Ursina's ``Audio`` (Panda3D OpenAL) exposes a per-sound ``pitch``
property, but support for changing it mid-playback varies by backend
and it cannot be exercised at all in this headless sandbox (the audio
device falls back to NullAudioManager). The mechanism that provably
works everywhere — and the one shipped — is PRE-RENDERED VARIANTS:

  * ``generate_audio_assets.py`` renders every asset twice: the normal
    file in ``assets/`` and a 0.4x-speed resample in
    ``assets/bullet_time/`` (same samples stretched to 2.5x duration,
    so pitch drops to 0.4x — proven numerically by test_audio_math.py).
  * While Bullet Time is active the manager switches variants: BGM
    restarts from the bullet_time/ file, and every SFX/UI triggered
    during Bullet Time plays its variant.
  * The manager still sets ``Audio.pitch = time_scale`` when it enters
    Bullet Time as a best-effort enhancement on backends that honour
    it; correctness never depends on it.

All v1 assets are SYNTHESIZED (numpy) — no licensed audio exists yet.
See generate_audio_assets.py and assets/manifest.json.
"""

from __future__ import annotations

import logging
import time as _time
from pathlib import Path
from typing import Optional

from ursina import Audio

from phase4.assets import asset_path

logger = logging.getLogger(__name__)

BULLET_TIME_PITCH = 0.4

BGM_FILE = "bgm_loop.wav"
SFX_FILES = {
    "gunshot": "sfx_gunshot.wav",
    "casing": "sfx_casing.wav",
    "slide": "sfx_slide.wav",
    "glass_break": "sfx_glass_break.wav",
    "melee_hit": "sfx_melee_hit.wav",
    "server_explosion": "sfx_server_explosion.wav",
}
UI_FILES = {
    "charge": "ui_charge.wav",       # Bullet Time charge-ready beep
    "combo": "ui_combo.wav",         # combo registration blip
    "rank": "ui_rank.wav",           # final rank announcement sting
}


class SoundManager:
    """Owns every Audio object the game plays. Construct after Ursina()."""

    def __init__(self, bgm_volume: float = 0.7, sfx_volume: float = 0.9,
                 ui_volume: float = 0.8) -> None:
        self._volumes = {"bgm": float(bgm_volume), "sfx": float(sfx_volume),
                         "ui": float(ui_volume)}
        self.bullet_time = False
        self.time_scale = 1.0
        self._bgm: Optional[Audio] = None
        self._bgm_started_at = 0.0     # monotonic clock when BGM (re)started
        self._live: list = []          # one-shot Audio objects in flight
        logger.info("SoundManager ready (bullet-time pitch x%.1f via "
                    "pre-rendered variants)", BULLET_TIME_PITCH)

    # ---------------------------------------------------------------- paths
    # NOTE: Ursina 8.3's Audio() only loads reliably from pathlib.Path
    # objects (string paths warn "missing audio clip" and yield no
    # sound) — verified by probe in this project. Always pass Paths.
    def _resolve_normal(self, filename: str) -> Path:
        return asset_path("assets", filename)

    def _resolve_variant(self, filename: str) -> Path:
        return asset_path("assets", "bullet_time", filename)

    # -------------------------------------------------------------- volumes
    def set_volume(self, channel: str, value: float) -> None:
        if channel not in self._volumes:
            raise ValueError(f"unknown audio channel {channel!r}")
        self._volumes[channel] = max(0.0, min(1.0, float(value)))
        if channel == "bgm" and self._bgm is not None:
            self._bgm.volume = self._volumes["bgm"]

    def volume(self, channel: str) -> float:
        return self._volumes[channel]

    # ------------------------------------------------------------------ BGM
    def start_bgm(self) -> None:
        """Start (or restart) the looping BGM at the current time scale."""
        self.stop_bgm()
        filename = BGM_FILE
        path = self._resolve_variant(filename) if self.bullet_time \
            else self._resolve_normal(filename)
        self._bgm = Audio(path, loop=True, autoplay=True,
                          volume=self._volumes["bgm"])
        try:
            self._bgm.pitch = self.time_scale
        except Exception:  # backend without pitch support: variants carry it
            logger.debug("Audio.pitch unsupported on this backend")
        self._bgm_started_at = _time.monotonic()
        logger.info("BGM started (%s)", Path(path).parent.name + "/" + filename)

    def stop_bgm(self) -> None:
        if self._bgm is not None:
            self._bgm.stop()
            self._bgm = None

    @property
    def bgm_playing(self) -> bool:
        return self._bgm is not None and bool(self._bgm.playing)

    # ------------------------------------------------------------------ SFX
    def play_sfx(self, name: str) -> Optional[Audio]:
        """Play a named one-shot SFX (Bullet-Time variant while slowed)."""
        if name not in SFX_FILES:
            raise ValueError(f"unknown sfx {name!r}; have {sorted(SFX_FILES)}")
        return self._play_one_shot(SFX_FILES[name], self._volumes["sfx"])

    def play_ui(self, name: str) -> Optional[Audio]:
        """Play a named UI cue ('charge' | 'combo' | 'rank')."""
        if name not in UI_FILES:
            raise ValueError(f"unknown ui cue {name!r}; have {sorted(UI_FILES)}")
        return self._play_one_shot(UI_FILES[name], self._volumes["ui"])

    def _play_one_shot(self, filename: str, volume: float) -> Optional[Audio]:
        path = self._resolve_variant(filename) if self.bullet_time \
            else self._resolve_normal(filename)
        clip = Audio(path, loop=False, autoplay=True, volume=volume)
        try:
            clip.pitch = self.time_scale
        except Exception:
            logger.debug("Audio.pitch unsupported on this backend")
        self._live.append(clip)
        return clip

    # ------------------------------------------------------------ bullet time
    def set_bullet_time(self, active: bool) -> None:
        """Switch the whole mix to/from the 0.4x Bullet-Time variants."""
        active = bool(active)
        if active == self.bullet_time:
            return
        self.bullet_time = active
        self.time_scale = BULLET_TIME_PITCH if active else 1.0
        logger.info("Bullet Time audio %s (pitch x%.1f)",
                    "ON" if active else "OFF", self.time_scale)
        if self._bgm is not None:
            self.start_bgm()  # crossfade: restart BGM from the other variant

    # ------------------------------------------------------------------ misc
    def prune(self) -> None:
        """Drop finished one-shot clips (call once per frame from update)."""
        self._live = [c for c in self._live if c.playing]

    @property
    def live_clip_count(self) -> int:
        return len(self._live)
