"""Build driver for the standalone game executable.

Runs PyInstaller against main.spec and reports the result honestly:
  * Linux build is produced + smoke-run HERE (headless, xvfb).
  * A Windows .exe CANNOT be produced from Linux — PyInstaller does
    not cross-compile. PACKAGING.md carries the one-command Windows
    build. This script never fabricates an .exe.

Usage:  python build_executable.py [--skip-smoke]
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DIST = PROJECT_ROOT / "dist" / "ActionStarNYCSiege"


def main() -> int:
    skip_smoke = "--skip-smoke" in sys.argv
    cmd = [sys.executable, "-m", "PyInstaller", str(HERE / "main.spec"),
           "--noconfirm", "--distpath", str(PROJECT_ROOT / "dist"),
           "--workpath", str(PROJECT_ROOT / "build")]
    print("BUILD:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if proc.returncode != 0:
        print(f"BUILD FAILED (PyInstaller exit {proc.returncode})")
        return proc.returncode

    binary = DIST / "ActionStarNYCSiege"
    exe = DIST / "ActionStarNYCSiege.exe"
    produced = exe if exe.exists() else binary
    if not produced.exists():
        print("BUILD FAILED: no executable produced in", DIST)
        return 1
    size_mb = produced.stat().st_size / 1e6
    print(f"BUILD OK: {produced} ({size_mb:.1f} MB)")

    if sys.platform.startswith("win"):
        print("This IS the Windows .exe build.")
    else:
        print("NOTE: this is the LINUX binary. The Windows .exe must be "
              "built on Windows — see PACKAGING.md.")

    if skip_smoke:
        return 0
    print("SMOKE: launching the binary headless for 12s ...", flush=True)
    run = subprocess.Popen(
        ["xvfb-run", "-a", str(produced)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(12)
        alive = run.poll() is None
    finally:
        run.terminate()
        try:
            out, _ = run.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            run.kill()
            out, _ = run.communicate()
    markers = [line for line in (out or "").splitlines()
               if "SoundManager ready" in line or "MainMenuState" in line
               or "BGM started" in line]
    print("SMOKE log markers:", markers if markers else "(none found)")
    print("SMOKE process alive after 12s:", alive)
    ok = alive and len(markers) >= 2
    print("SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
