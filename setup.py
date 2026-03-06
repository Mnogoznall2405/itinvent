import runpy
from pathlib import Path

TARGET_SETUP = Path(__file__).resolve().parent / "agent" / "setup.py"

if __name__ == "__main__":
    print("[compat] setup.py moved to agent/setup.py")
    runpy.run_path(str(TARGET_SETUP), run_name="__main__")
