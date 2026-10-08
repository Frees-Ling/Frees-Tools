"""Build and smoke-test the current native platform. Never cross-compiles."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
import tempfile
from PIL import Image

root = Path(__file__).resolve().parents[1]
os.chdir(root)
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "Frees-Tools",
        "--collect-all",
        "textual",
        "--collect-all",
        "frees_tools",
        "--collect-all",
        "PIL",
        "--collect-all",
        "pypdf",
        "--copy-metadata",
        "frees-tools",
        "scripts/launcher.py",
    ],
    check=True,
)
folder = root / "dist" / "Frees-Tools"
ext = ".exe" if os.name == "nt" else ""
exe = folder / ("Frees-Tools" + ext)
# Two actual entry files. Windows and default macOS filesystems ignore case.
# On Linux both real launchers are required.
if platform.system() == "Linux":
    shutil.copy2(exe, folder / "frees-tools")
else:
    alias = folder / ("frees-tools.cmd" if os.name == "nt" else "frees-tools")
    if os.name == "nt":
        alias.write_text('@"%~dp0Frees-Tools.exe" %*\n')
    elif not alias.exists():
        alias.symlink_to("Frees-Tools")
for args in (["--version"], ["--help"], ["--json", "doctor"]):
    result = subprocess.run(
        [str(exe), *args], check=True, capture_output=True, text=True, timeout=90
    )
    if "--json" in args:
        json.loads(result.stdout)
license_dir = folder / "THIRD_PARTY_LICENSES"
license_dir.mkdir(exist_ok=True)
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name", "unknown")
    if name.lower() in {
        "pytest",
        "pytest-asyncio",
        "ruff",
        "build",
        "iniconfig",
        "pluggy",
        "frees-tools",
    }:
        continue
    for item in distribution.files or []:
        if any(word in item.name.lower() for word in ("license", "copyright", "notice")):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                target = license_dir / name / str(item).replace("..", "_").replace("/", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
shutil.copy2("LICENSE", folder / "LICENSE")
shutil.copy2("docs/THIRD_PARTY.md", folder / "THIRD_PARTY.md")
shutil.copy2("docs/INSTALL.md", folder / "INSTALL.md")
# Frozen smoke test processes real generated images and PDF without Python installed.
with tempfile.TemporaryDirectory() as name:
    temp = Path(name)
    Image.new("RGBA", (32, 24), (255, 0, 0, 120)).save(temp / "中文 image.png")
    for args in (
        [
            "image",
            "convert",
            str(temp / "中文 image.png"),
            "--to",
            "jpg",
            "--output",
            str(temp / "out.jpg"),
        ],
        ["pdf", "from-images", str(temp / "out.jpg"), "--output", str(temp / "out.pdf")],
        ["pdf", "info", str(temp / "out.pdf")],
    ):
        subprocess.run(
            [str(exe), "--json", *args], check=True, capture_output=True, text=True, timeout=90
        )
system = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}[platform.system()]
arch = {"arm64": "arm64", "aarch64": "arm64", "AMD64": "x64", "x86_64": "x64"}[platform.machine()]
base = f"Frees-Tools-v0.1.0-{system}-{arch}"
if os.name == "nt":
    archive = root / "dist" / (base + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for item in folder.rglob("*"):
            z.write(item, item.relative_to(folder.parent))
else:
    archive = root / "dist" / (base + ".tar.gz")
    with tarfile.open(archive, "w:gz") as t:
        t.add(folder, arcname=folder.name)
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n")
print(archive)
