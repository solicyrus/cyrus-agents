"""Phase 4 — menus, dynamic audio, high scores, packaging.

Action Star: NYC Siege 3D finalization workstream A:
  assets.py          asset_path() (_MEIPASS-safe) + user-data paths
  sound_manager.py   BGM/SFX/UI pipeline + Bullet-Time pitch variants
  scores_store.py    per-stage best takes (JSON, user-data folder)
  game_settings.py   persisted settings + engine application
  game_ui_screens.py Settings / Victory / High Scores screens
  main_menu.py       MainMenuState — cinematic 3D menu + state machine
  game_entry.py      the packaged game entry (menu shell)
  build_executable.py  PyInstaller build driver (see main.spec)
"""
