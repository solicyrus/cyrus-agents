"""Menu + screens smoke test — Phase 4 (headless, xvfb).

Drives the REAL Phase-4 UI programmatically, no mouse:
  menu -> HIGH SCORES (empty table) -> settings (volume / resolution /
  graphics / key guide) -> record a take -> HIGH SCORES shows it ->
  VICTORY card (A / Box Office Hit, 11,800) -> RE-TAKE -> card again ->
  BACK TO MENU -> GAME OVER state (F / Re-take Required) -> stage start.

Also constructs the SoundManager and fires SFX/UI + a Bullet-Time
switch. NOTE: this sandbox has NO audio device (Panda3D falls back to
NullAudioManager), so clips are asserted as constructed objects, not
as audible playback.

Run:  xvfb-run -a python test_menu_smoke.py   (exit 0 = PASS)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="actionstar-smoke-")
os.environ["ACTION_STAR_DATA_DIR"] = _TMP  # scores/settings land in tmp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ursina import Entity, Ursina, application, window  # noqa: E402

from logic.take_rating import evaluate  # noqa: E402
from phase4.game_settings import load_settings  # noqa: E402
from phase4.game_ui_screens import (HighScoresScreen, SettingsMenu,  # noqa: E402
                                    VictoryScreen)
from phase4.main_menu import MainMenuState  # noqa: E402
from phase4.scores_store import ScoresStore  # noqa: E402
from phase4.sound_manager import SoundManager  # noqa: E402

RESULTS = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), label))
    print(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}", flush=True)


app = Ursina(title="Action Star — Phase 4 smoke", vsync=False)

settings = load_settings()
sound = SoundManager(bgm_volume=settings.bgm_volume,
                     sfx_volume=settings.sfx_volume,
                     ui_volume=settings.ui_volume)
store = ScoresStore()

events = {"start": [], "retake": [], "menu": 0}
menu = MainMenuState()
settings_screen = SettingsMenu(settings, sound_manager=sound,
                               on_back=lambda: menu.show())
scores_screen = HighScoresScreen(store, on_back=lambda: menu.show())
victory = VictoryScreen(
    sound_manager=sound,
    on_retake=lambda sid: events["retake"].append(sid),
    on_menu=lambda: events.__setitem__("menu", events["menu"] + 1))
menu.on_start = lambda sid: events["start"].append(sid)
menu.on_settings = lambda: settings_screen.show()
menu.on_scores = lambda: scores_screen.show()
menu.show()
sound.start_bgm()

RECORD = {"stage_id": "lobby", "stage_name": "Lobby", "t_actual": 85.0,
          "t_target": 90.0, "combo_peak": 2.5, "completed": True,
          "stunt_breakdown": ["Bullet Dodge x4", "Slide & Shoot x3"]}


def step_scores_empty() -> None:
    menu.press_scores()
    check(menu.last_action == "scores" and scores_screen.visible,
          "menu -> HIGH SCORES opens")
    check("No takes yet" in scores_screen.lines.text,
          "empty table is honest", scores_screen.lines.text.splitlines()[0])
    scores_screen.press_back()
    check(not scores_screen.visible, "scores BACK closes")


def step_settings() -> None:
    menu.press_settings()
    check(settings_screen.visible, "menu -> SETTINGS opens")
    settings_screen.set_bgm_volume(0.5)
    check(abs(settings.bgm_volume - 0.5) < 1e-9
          and abs(sound.volume("bgm") - 0.5) < 1e-9,
          "BGM slider applies live to settings + SoundManager",
          f"bgm={settings.bgm_volume}")
    settings_screen.set_resolution(1600, 900)
    check(settings.resolution == (1600, 900), "resolution selector applies",
          f"window.size={window.size}")
    settings_screen.set_graphics("Low")
    check(settings.graphics == "Low" and window.vsync is False,
          "graphics selector applies (Low -> vsync off)")
    guide = settings_screen.key_guide.text
    check("L-SHIFT" in guide and "Bullet Time" in guide and "Slide" in guide,
          "key-guide panel lists the real controls")
    settings_screen.press_back()
    check(not settings_screen.visible, "settings BACK closes")


def step_record_and_scores() -> None:
    became = store.record("lobby", s_total=11800, rank="A",
                          title="Box Office Hit", s_time=3500,
                          stunt_base=3320, combo_multiplier=2.5,
                          t_actual=85.0, t_target=90.0)
    check(became, "victory flow writes the take to the store")
    menu.press_scores()
    text = scores_screen.lines.text
    check("11,800" in text and "Box Office Hit" in text,
          "HIGH SCORES lists the recorded best", text.splitlines()[0])
    scores_screen.press_back()


def step_victory() -> None:
    result = evaluate(s_time=3500, s_stunt=3320, m_combo=2.5)
    victory.show_result(result, RECORD)
    check(victory.outcome == "victory" and victory.visible,
          "victory state renders")
    check(victory.rank_text.text == "A"
          and victory.title_text.text == "Box Office Hit",
          "rank card: A / Box Office Hit")
    check("11,800" in victory.breakdown.text
          and "3,500" in victory.breakdown.text,
          "breakdown shows S_time + total", victory.breakdown.text.splitlines()[-1])
    victory.press_retake()
    check(events["retake"] == ["lobby"] and not victory.visible,
          "RE-TAKE fires with the stage id")
    victory.show_result(result, RECORD)
    victory.press_menu()
    check(events["menu"] == 1 and menu.active,
          "BACK TO MENU returns to the menu")


def step_game_over() -> None:
    result = evaluate(s_time=500, s_stunt=400, m_combo=1.0)  # 900 -> F
    victory.show_result(result, RECORD)
    check(victory.outcome == "game_over" and victory.rank_text.text == "F"
          and victory.title_text.text == "Re-take Required",
          "F total renders the Game Over state")
    victory.hide()
    good = evaluate(s_time=3500, s_stunt=3320, m_combo=2.5)
    dnf = dict(RECORD, completed=False)
    victory.show_result(good, dnf)
    check(victory.outcome == "game_over",
          "an unfinished run renders Game Over even with a good score")
    victory.press_menu()


def step_sound_and_start() -> None:
    clip = sound.play_sfx("gunshot")
    ui = sound.play_ui("combo")
    check(clip is not None and ui is not None, "SFX + UI clips construct")
    sound.set_bullet_time(True)
    check(sound.bullet_time and abs(sound.time_scale - 0.4) < 1e-9
          and sound._bgm is not None,
          "Bullet Time switches the mix to 0.4x variants")
    sound.set_bullet_time(False)
    check(abs(sound.time_scale - 1.0) < 1e-9, "Bullet Time exit restores 1.0x")
    menu.press_start()
    check(events["start"] == ["lobby"] and menu.last_stage == "lobby",
          "START GAME launches the Lobby")
    menu.press_stage_select()
    menu.press_stage("penthouse")
    check(events["start"][-1] == "penthouse",
          "STAGE SELECT launches the Penthouse")


STEPS = [step_scores_empty, step_settings, step_record_and_scores,
         step_victory, step_game_over, step_sound_and_start]


class Driver(Entity):
    def __init__(self) -> None:
        super().__init__()
        self.frame = 0
        self.idx = 0

    def update(self) -> None:
        self.frame += 1
        menu.update(1 / 60)
        if self.frame % 25 == 0 and self.idx < len(STEPS):
            STEPS[self.idx]()
            self.idx += 1
        elif self.idx >= len(STEPS) and self.frame % 25 == 0:
            failed = [label for ok, label in RESULTS if not ok]
            print(f"PROOF menu smoke: {sum(ok for ok, _ in RESULTS)}/"
                  f"{len(RESULTS)} checks passed, frames={self.frame}",
                  flush=True)
            print("PROOF " + ("ALL PASS" if not failed
                              else f"FAILURES {failed}"), flush=True)
            application.quit()


driver = Driver()
app.run()

_failed = [label for ok, label in RESULTS if not ok]
sys.exit(1 if _failed or not RESULTS else 0)
