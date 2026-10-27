"""QA tests for save_system.SaveManager + level_select.LevelSelectMenu.

Part A — pure logic (any Python, no engine):
  * fresh profile: only Level 1 unlocked, all records zeroed;
  * save_stage_result(1, 14500, 68.4, "A") stores the record and
    unlocks Level 2 (Level 3 stays locked);
  * an "F" take records its score but does NOT unlock;
  * a lower score never overwrites the best-scoring take (its time
    and rank travel with it);
  * state persists identically across a reload from disk;
  * a corrupt JSON file loads as a fresh profile, no crash;
  * the unlock chain caps at Level 3 (no Level 4 ever appears).

Part B — headless Ursina smoke (xvfb + the project venv):
  builds LevelSelectMenu on a seeded SaveManager (Level 1 cleared
  with 14500 / rank A, Level 2 unlocked, Level 3 locked) and asserts
  the card texts, that a programmatic click on the locked card fires
  NOTHING, and that a click on Level 2 fires on_level_chosen(2).

Run:
  python3 test_save_system.py                      (Part A only)
  xvfb-run -a /tmp/ursina-venv/bin/python \
      test_save_system.py --require-ui             (Part A + B)

Exit code 0 = PASS, 1 = FAIL. PROOF lines go to stdout.
"""

import json
import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from save_system import SaveManager, default_save_path  # noqa: E402

results = {"failures": [], "checks": 0}


def check(name, ok, detail=""):
    results["checks"] += 1
    line = f"PROOF check {name}: {'OK' if ok else 'FAIL'} {detail}".rstrip()
    print(line, flush=True)
    if not ok:
        results["failures"].append(name)


# --------------------------------------------------------------------------
# Part A — pure logic
# --------------------------------------------------------------------------
def run_logic_tests():
    tmp = tempfile.mkdtemp(prefix="actionstar-save-")
    path = os.path.join(tmp, "user_progress.json")

    # -- fresh profile ------------------------------------------------------
    mgr = SaveManager(save_path=path)
    check("fresh_only_level1_unlocked", mgr.unlocked_levels == [1],
          f"unlocked={mgr.unlocked_levels}")
    check("fresh_is_unlocked_flags",
          mgr.is_unlocked(1) and not mgr.is_unlocked(2)
          and not mgr.is_unlocked(3) and not mgr.is_unlocked(4))
    rec = mgr.get_level_record(1)
    check("fresh_record_zeroed",
          rec == {"title": "NYC Tower Lobby", "best_score": 0,
                  "best_time": 0.0, "best_rank": "N/A"},
          f"record={rec}")
    check("fresh_titles",
          mgr.get_level_record(2)["title"] == "Data Center"
          and mgr.get_level_record(3)["title"] == "Penthouse & Helipad")

    # -- a passing take: record stored + Level 2 unlocked -------------------
    improved = mgr.save_stage_result(1, 14500, 68.4, "A")
    rec = mgr.get_level_record(1)
    check("record_stored", improved and rec["best_score"] == 14500
          and rec["best_time"] == 68.4 and rec["best_rank"] == "A",
          f"record={rec}")
    check("pass_unlocks_level2", mgr.unlocked_levels == [1, 2],
          f"unlocked={mgr.unlocked_levels}")
    check("level3_still_locked", not mgr.is_unlocked(3))

    # -- a lower score never overwrites the best take -----------------------
    improved = mgr.save_stage_result(1, 5000, 40.0, "S")
    rec = mgr.get_level_record(1)
    check("lower_score_keeps_record",
          not improved and rec["best_score"] == 14500
          and rec["best_time"] == 68.4 and rec["best_rank"] == "A",
          f"record={rec}")

    # -- persistence across reload ------------------------------------------
    before = json.loads(json.dumps(mgr.data))
    mgr2 = SaveManager(save_path=path)
    check("reload_persists_identically", mgr2.data == before,
          f"reloaded={mgr2.data}")

    # -- an F take records its score but does NOT unlock --------------------
    path_f = os.path.join(tmp, "f_profile.json")
    mgr_f = SaveManager(save_path=path_f)
    mgr_f.save_stage_result(1, 9000, 80.0, "F")
    rec_f = mgr_f.get_level_record(1)
    check("f_take_records_score",
          rec_f["best_score"] == 9000 and rec_f["best_rank"] == "F",
          f"record={rec_f}")
    check("f_take_does_not_unlock", mgr_f.unlocked_levels == [1],
          f"unlocked={mgr_f.unlocked_levels}")

    # -- unlock chain caps at Level 3 ---------------------------------------
    mgr.save_stage_result(2, 16200, 59.1, "S")
    check("level2_pass_unlocks_level3", mgr.unlocked_levels == [1, 2, 3],
          f"unlocked={mgr.unlocked_levels}")
    mgr.save_stage_result(3, 21000, 97.5, "S")
    check("no_level4_ever", mgr.unlocked_levels == [1, 2, 3]
          and not mgr.is_unlocked(4),
          f"unlocked={mgr.unlocked_levels}")

    # -- corrupt file -> fresh profile, no crash -----------------------------
    path_bad = os.path.join(tmp, "corrupt.json")
    with open(path_bad, "w", encoding="utf-8") as handle:
        handle.write("{ this is not json !!!")
    mgr_bad = SaveManager(save_path=path_bad)
    check("corrupt_file_loads_defaults",
          mgr_bad.unlocked_levels == [1]
          and mgr_bad.get_level_record(1)["best_score"] == 0)

    # -- save path sanity -----------------------------------------------------
    default_path = default_save_path()
    check("default_path_shape",
          default_path.endswith("user_progress.json")
          and ("ActionStar" in default_path
               or ".actionstar" in default_path),
          f"default={default_path}")


# --------------------------------------------------------------------------
# Part B — headless Ursina smoke
# --------------------------------------------------------------------------
def run_ui_smoke():
    from ursina import Ursina, application

    app = Ursina(title="Action Star — Level Select smoke", vsync=False)
    _ = app  # the engine object must exist before any Entity is built

    from level_select import LevelSelectMenu

    tmp = tempfile.mkdtemp(prefix="actionstar-ui-")
    mgr = SaveManager(save_path=os.path.join(tmp, "user_progress.json"))
    mgr.save_stage_result(1, 14500, 68.4, "A")   # clears 1, unlocks 2

    chosen = []
    backs = []
    menu = LevelSelectMenu(mgr, on_level_chosen=chosen.append,
                           on_back=lambda: backs.append(True))

    text1 = menu.card_text(1)
    check("card1_shows_record", "14500" in text1 and "Rank: A" in text1
          and "68.4" in text1 and "NYC Tower Lobby" in text1,
          f"card1={text1!r}")
    text2 = menu.card_text(2)
    check("card2_unlocked_no_lock", "🔒" not in text2
          and "Data Center" in text2, f"card2={text2!r}")
    text3 = menu.card_text(3)
    check("card3_shows_lock", "🔒" in text3 and "LOCKED" in text3,
          f"card3={text3!r}")

    result = menu.activate_card(3)
    check("locked_card_click_fires_nothing",
          result is None and chosen == [],
          f"result={result} chosen={chosen}")
    menu.cards[3].on_click()
    check("locked_button_handler_fires_nothing", chosen == [],
          f"chosen={chosen}")

    result = menu.activate_card(2)
    check("unlocked_card_click_fires_callback",
          result == 2 and chosen == [2],
          f"result={result} chosen={chosen}")
    menu.cards[1].on_click()
    check("unlocked_button_handler_fires_callback", chosen == [2, 1],
          f"chosen={chosen}")

    menu.back_button.on_click()
    check("back_button_fires_on_back", backs == [True],
          f"backs={backs}")

    menu.destroy()
    application.quit()


def main():
    run_logic_tests()
    if "--require-ui" in sys.argv:
        run_ui_smoke()
    else:
        try:
            import ursina  # noqa: F401
            run_ui_smoke()
        except ImportError:
            print("PROOF ui_smoke SKIPPED: ursina not importable in this "
                  "interpreter — rerun with --require-ui under "
                  "xvfb-run + /tmp/ursina-venv/bin/python", flush=True)
    verdict = "PASS" if not results["failures"] else "FAIL"
    print(f"PROOF save_system {verdict}: {results['checks']} checks, "
          f"{len(results['failures'])} failures", flush=True)
    return 0 if not results["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
