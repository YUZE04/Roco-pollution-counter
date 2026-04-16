import os
import re
import sys
import importlib.util
from pathlib import Path

from cx_Freeze import Executable, setup


REPO_ROOT = Path(__file__).resolve().parent
SOURCE_FILE = REPO_ROOT / "1.py"
ICON_FILE = REPO_ROOT / "roco_counter_icon.ico"

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def read_app_version() -> str:
    source = SOURCE_FILE.read_text(encoding="utf-8")
    match = re.search(r'"app_version"\s*:\s*"v?([^"]+)"', source)
    if match:
        return match.group(1)
    return "1.1.0"


APP_VERSION = read_app_version()
TARGET_EXE = f"污染计数器_v{APP_VERSION}.exe"

RAW_RUNTIME_MODULES = [
    "bidi",
    "certifi",
    "chardet",
    "charset_normalizer",
    "click",
    "crc32c",
    "Crypto",
    "dateutil",
    "filelock",
    "google",
    "hf_xet",
    "idna",
    "imagesize",
    "markupsafe",
    "numpy",
    "numpy.libs",
    "paddle",
    "paddleocr",
    "paddlex",
    "pandas",
    "pandas.libs",
    "PIL",
    "prettytable",
    "psutil",
    "pyclipper",
    "pydantic",
    "pydantic_core",
    "pypdfium2",
    "pypdfium2_raw",
    "requests",
    "ruamel",
    "safetensors",
    "scipy",
    "scipy.libs",
    "shapely",
    "Shapely.libs",
    "skimage",
    "tqdm",
    "typing_extensions",
    "tzdata",
    "ujson",
    "urllib3",
    "wcwidth",
    "yaml",
]

EXTRA_RUNTIME_DIRS = {
    "numpy.libs": "numpy",
    "pandas.libs": "pandas",
    "scipy.libs": "scipy",
    "Shapely.libs": "shapely",
}


def build_raw_runtime_entries():
    entries: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for module_name in RAW_RUNTIME_MODULES:
        if module_name in EXTRA_RUNTIME_DIRS:
            anchor_spec = importlib.util.find_spec(EXTRA_RUNTIME_DIRS[module_name])
            if anchor_spec is None or not anchor_spec.origin:
                continue
            site_packages_dir = Path(anchor_spec.origin).resolve().parent.parent
            source_path = site_packages_dir / module_name
            if not source_path.exists():
                continue
            target_name = f"lib/{source_path.name}"
            key = (str(source_path), target_name)
            if key not in seen:
                seen.add(key)
                entries.append((str(source_path), target_name))
            continue
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            continue
        if spec.submodule_search_locations:
            source_path = Path(list(spec.submodule_search_locations)[0]).resolve()
            target_name = f"lib/{source_path.name}"
        elif spec.origin:
            source_path = Path(spec.origin).resolve()
            target_name = f"lib/{source_path.name}"
        else:
            continue
        key = (str(source_path), target_name)
        if key in seen:
            continue
        seen.add(key)
        entries.append((str(source_path), target_name))
    return entries

BUILD_EXE_OPTIONS = {
    "packages": [
        "keyboard",
        "mss",
        "tkinter",
    ],
    "includes": [
        "cv2",
    ],
    "include_files": [
        (str(ICON_FILE), "roco_counter_icon.ico"),
        (str(REPO_ROOT / "pollution_config.json"), "pollution_config.json"),
        (str(REPO_ROOT / "pollution_count.json"), "pollution_count.json"),
        *build_raw_runtime_entries(),
    ],
    "excludes": [
        *RAW_RUNTIME_MODULES,
        "jax",
        "jaxlib",
        "langchain",
        "langchain_core",
        "langchain_text_splitters",
        "tensorboard",
        "tensorflow",
        "torch",
        "torchaudio",
        "torchvision",
    ],
    "include_msvcr": True,
    "optimize": 0,
    "silent_level": 1,
    "zip_include_packages": [],
    "zip_exclude_packages": ["*"],
}

BASE = "gui" if sys.platform == "win32" else None


setup(
    name="pollution-counter",
    version=APP_VERSION,
    description="Roco pollution counter with local PaddleOCR models.",
    options={"build_exe": BUILD_EXE_OPTIONS},
    executables=[
        Executable(
            script=str(SOURCE_FILE),
            base=BASE,
            icon=str(ICON_FILE),
            target_name=TARGET_EXE,
        )
    ],
)
