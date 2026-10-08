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
import sysconfig
import tarfile
import zipfile
import tempfile
from PIL import Image


def run_checked(*args, **kwargs):
    try:
        return subprocess.run(*args, **kwargs)
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout[-6000:])
        if error.stderr:
            print(error.stderr[-6000:], file=sys.stderr)
        raise


root = Path(__file__).resolve().parents[1]
os.chdir(root)
run_checked(
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
        "--copy-metadata",
        "typer",
        "--copy-metadata",
        "platformdirs",
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
lower_entry = folder / ("frees-tools.exe" if os.name == "nt" else "frees-tools")
run_checked([str(lower_entry), "--version"], check=True, capture_output=True, timeout=90)
for args in (["--version"], ["--help"], ["--json", "doctor"]):
    result = run_checked(
        [str(exe), *args], check=True, capture_output=True, text=True, encoding="utf-8", timeout=90
    )
    if "--json" in args:
        json.loads(result.stdout)
license_dir = folder / "THIRD_PARTY_LICENSES"
license_dir.mkdir(exist_ok=True)
python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
if not python_license.exists():
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
if not python_license.exists():
    raise RuntimeError("Python runtime license missing; do not publish this build")
shutil.copy2(python_license, license_dir / "Python-LICENSE.txt")
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
        ["self-test"],
    ):
        run_checked(
            [str(exe), "--json", *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            env=os.environ | {"FREES_TOOLS_HOME": str(temp / "state")},
        )
# Exercise external adapters from the frozen program when build engines are available.
with tempfile.TemporaryDirectory() as name:
    temp = Path(name)
    environment = os.environ | {"FREES_TOOLS_HOME": str(temp / "state")}

    def frozen(*arguments):
        result = run_checked(
            [str(exe), "--json", *map(str, arguments)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            env=environment,
        )
        return json.loads(result.stdout)

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        run_checked(
            [
                shutil.which("ffmpeg"),
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x48:r=10:d=0.3",
                "-c:v",
                "mpeg4",
                str(temp / "input.mov"),
            ],
            check=True,
            timeout=30,
        )
        frozen(
            "video", "convert", temp / "input.mov", "--to", "mp4", "--output", temp / "output.mp4"
        )
        if not (temp / "output.mp4").is_file():
            raise RuntimeError("Frozen video smoke test did not produce output")
    if shutil.which("aria2c"):
        try:
            frozen("torrent", "list")
        finally:
            if (temp / "state" / "torrent" / "runtime.json").exists():
                frozen("torrent", "shutdown")
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
        if platform.system() == "Darwin" and not (folder / "frees-tools").is_symlink():
            # Include both binary names in the archive even on a case-insensitive build disk.
            # Extracting to either case-sensitive or default macOS filesystems remains safe.
            t.add(exe, arcname=folder.name + "/frees-tools")
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n")
print(archive)
