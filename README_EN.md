# Frees Tools

A terminal toolbox with a Textual interface and shared CLI services for images, PDF composition, FFmpeg conversion and aria2 BitTorrent downloads. Version: **0.1.0**.

Targets Windows x64, macOS arm64 / x64 and Linux x64. Actual validation and release status are recorded in [release readiness](docs/RELEASE_READINESS.md); workflow configuration alone does not prove platform compatibility. [中文说明](README.md).

## Install

Requires Python 3.11+ and Git for source installation. This project is not yet published on PyPI.

```console
pipx install git+https://github.com/Frees-Ling/Frees-Tools.git
Frees-Tools
```

Alternatively:

```console
uv tool install git+https://github.com/Frees-Ling/Frees-Tools.git
frees-tools
```

Both command names are installed. A bare command opens the TUI only when stdin and stdout are interactive; noninteractive use prints help. Native archives, when published, do not require a separate Python installation. See [installation](docs/INSTALL.md).

FFmpeg / ffprobe and aria2c are external dependencies and are **not bundled**. Install through your trusted system package manager: `brew install ffmpeg aria2` on macOS; `sudo apt install ffmpeg aria2` on Debian / Ubuntu; `winget install Gyan.FFmpeg` and `winget install aria2.aria2` on Windows. Restart the terminal, then run `Frees-Tools doctor`.

## Examples

```console
Frees-Tools image convert input.png --to jpg --output output.jpg --background "#ffffff"
Frees-Tools image batch ./images --to webp --output-dir ./converted --recursive
Frees-Tools pdf merge a.pdf b.pdf --output merged.pdf
Frees-Tools pdf from-images a.jpg b.png --paper a4 --output images.pdf
Frees-Tools pdf combine a.pdf b.jpg c.pdf --output combined.pdf
Frees-Tools video convert input.mov --to mp4 --preset balanced --output output.mp4
Frees-Tools video extract-audio input.mp4 --to mp3 --output output.mp3
Frees-Tools torrent add example.torrent --dir ./downloads
Frees-Tools torrent list
Frees-Tools torrent status TASK_ID
Frees-Tools torrent pause TASK_ID
Frees-Tools torrent resume TASK_ID
Frees-Tools torrent remove TASK_ID
Frees-Tools --json doctor
```

Every command has `--help`. Quote paths containing spaces. Outputs require explicit `--overwrite`; source files remain protected. Image conversion supports PNG, JPEG, WebP, BMP, TIFF and GIF. Animated / multipage inputs require explicit `--first-frame` consent to discard remaining frames. PDF composition includes all image frames, with auto / A4 / A3 / Letter paper and contain / cover fit. Password-protected PDFs must be decrypted beforehand. Video codec availability depends on the installed FFmpeg build.

TUI keys: Tab / Shift+Tab focus, arrows navigate, Enter confirm, Esc dashboard / close dialog, F1 help, Ctrl+T tasks, Ctrl+Q quit. The file browser supports navigation, path entry, ordered multiple selection and removal. The task center shows results and errors and allows cancellation. Local conversions are cancelled when the app exits; history persists, but restarting conversions requires resubmission. Download pause / resume is supported by aria2.

The authenticated loopback aria2 engine continues downloads after clients close. `Frees-Tools torrent shutdown` saves its session and stops it. Removing a task preserves downloaded data by default; deleting data requires an explicit second confirmation, or both `--delete-data --yes` for automation.

Configuration uses platform user directories; `doctor` shows the location. `FREES_TOOLS_HOME` overrides configuration / state storage for isolated tests. See [architecture](docs/ARCHITECTURE.md), [build and release](docs/BUILD.md), and [third-party notices](docs/THIRD_PARTY.md). Project code is MIT licensed; bundled dependencies retain their own licenses.
