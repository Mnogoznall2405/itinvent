import os
import sys
import shutil
from pathlib import Path
from cx_Freeze import setup, Executable

sys.setrecursionlimit(10000)

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_SRC = REPO_ROOT / "agent" / "src"
AGENT_ENTRY = REPO_ROOT / "agent.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

# Use project-local temp path to avoid permission issues in user profile temp.
BUILD_TMP = REPO_ROOT / "tmp" / "cxfreeze"
BUILD_TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(BUILD_TMP)
os.environ["TEMP"] = str(BUILD_TMP)

# Some environments lock dist-info folders during cx_Freeze temporary cleanup.
# Do not fail build on temp cleanup errors.
_original_rmtree = shutil.rmtree

def _safe_rmtree(path, *args, **kwargs):
    kwargs["ignore_errors"] = True
    try:
        return _original_rmtree(path, *args, **kwargs)
    except Exception:
        return None

shutil.rmtree = _safe_rmtree

base = "Win32GUI" if sys.platform == "win32" else None

executables = [
    Executable(
        str(AGENT_ENTRY),
        base=base,
        target_name="ITInventAgent.exe",
        shortcut_name="IT-Invent Agent",
    )
]

build_exe_options = {
    "excludes": [
        "tkinter",
        "unittest",
        "watchdog",
        "watchdog.events",
        "watchdog.observers",
        "watchdog.observers.api",
    ],
    "packages": ["wmi", "psutil", "requests", "scan_agent", "yaml", "itinvent_agent"],
    "includes": ["scan_agent.agent", "fitz"],
    "include_files": [(str(REPO_ROOT / "patterns_strict.yaml"), "patterns_strict.yaml")],
    "include_msvcr": True,
}

bdist_msi_options = {
    "add_to_path": False,
    "initial_target_dir": r"[ProgramFiles64Folder]\\IT-Invent\\Agent",
    "all_users": True,
}

setup(
    name="IT-Invent Agent",
    version="1.2.3",
    author="IT-Invent",
    description="IT-Invent Unified Agent (Inventory + Scan)",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)
