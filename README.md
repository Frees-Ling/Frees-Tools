# Frees Tools

跨平台终端工具箱：在同一个 Textual 界面中转换图片、合成 PDF、转换视频、管理 BitTorrent 下载，也可以用 CLI 自动化调用。

项目版本：**0.1.0**。Windows x64、macOS arm64 / x64、Linux x64 已通过真实测试与原生包运行检查。详细证据和已知限制见 [实施记录](docs/IMPLEMENTATION_STATUS.md) 与 [发布检查](docs/RELEASE_READINESS.md)。

[English](README_EN.md) · [安装手册](docs/INSTALL.md) · [架构](docs/ARCHITECTURE.md) · [构建与发布](docs/BUILD.md)

## 安装与启动

源码安装需要 Python 3.11+ 和 Git。PyPI 尚未发布，不要依赖 `pip install frees-tools` 安装本项目。

```console
pipx install git+https://github.com/Frees-Ling/Frees-Tools.git
Frees-Tools
```

也可以使用 uv：

```console
uv tool install git+https://github.com/Frees-Ling/Frees-Tools.git
frees-tools
```

两个大小写形式均为安装入口。只有不带子命令、且输入输出都是交互式终端时才打开 TUI；重定向或流水线环境会输出帮助并退出。独立发行包的使用方式见安装手册，实际可下载资产以 [GitHub Releases](https://github.com/Frees-Ling/Frees-Tools/releases) 为准。

图片和 PDF 功能使用 Python 包中的依赖。视频需要系统提供 `ffmpeg` 与 `ffprobe`，BT 下载需要 `aria2c`。发行包不附带这两个外部引擎，也不会自动下载可执行文件。

```console
# macOS，已安装 Homebrew
brew install ffmpeg aria2
# Ubuntu / Debian
sudo apt install ffmpeg aria2
# Windows PowerShell，已安装 winget
winget install Gyan.FFmpeg
winget install aria2.aria2
```

安装后重新打开终端，运行：

```console
Frees-Tools doctor
Frees-Tools --json doctor
```

## 常用操作

路径含空格或中文时用引号包围。输出文件存在时默认拒绝覆盖；`--overwrite` 只允许覆盖输出，不能覆盖输入源文件。

```console
Frees-Tools --help
Frees-Tools --version
Frees-Tools image info "图片.png"
Frees-Tools image convert "图片.png" --to jpg --output "结果.jpg" --background "#ffffff"
Frees-Tools image convert input.jpg --to webp --output small.webp --width 1280 --quality 85
Frees-Tools image batch ./images --to webp --output-dir ./converted --recursive --pattern "*.png"
Frees-Tools pdf merge a.pdf b.pdf --output merged.pdf
Frees-Tools pdf from-images a.jpg b.png --output images.pdf --paper a4
Frees-Tools pdf combine a.pdf b.jpg c.pdf --output combined.pdf --fit contain
Frees-Tools pdf info combined.pdf
Frees-Tools video info input.mov
Frees-Tools video convert input.mov --to mp4 --preset balanced --output output.mp4
Frees-Tools video extract-audio input.mp4 --to mp3 --output output.mp3
Frees-Tools torrent add ./example.torrent --dir ./downloads
Frees-Tools torrent list
Frees-Tools torrent status TASK_ID
Frees-Tools torrent pause TASK_ID
Frees-Tools torrent resume TASK_ID
Frees-Tools torrent retry TASK_ID
Frees-Tools torrent remove TASK_ID
Frees-Tools tasks
```

所有子命令支持 `--help`。自动化输出使用全局选项，例如 `Frees-Tools --json pdf info document.pdf`；成功返回 0，参数或任务错误返回非零退出码。

## 功能与行为

- 图片支持 PNG、JPEG、WebP、BMP、TIFF、GIF；可设置质量、宽高上限、百分比缩放和透明背景颜色。宽高参数保持比例，`--scale 50` 表示缩至 50%，不可与宽高同时设置。先应用 EXIF 方向。动画 GIF / 多页 TIFF 默认拒绝单帧转换，必须用 `--first-frame` 明确舍弃其他帧。AVIF、HEIC 不属于首版保证范围。
- 图片批量转换保存相对子目录、报告逐文件结果和失败原因。不同源文件映射到同一输出名时报告冲突。
- PDF 按参数顺序合并 PDF 或图片，图片包含的全部帧按顺序进入 PDF。纸张支持 `auto`、`a4`、`a3`、`letter`；`contain` 完整显示，`cover` 铺满并裁切。自动图片页面按 96 DPI 生成，透明区域填白。密码保护 PDF 需要用户先解密；服务不接受密码参数。
- 视频支持 MP4、MOV、MKV、WebM，音频输出 MP3、WAV、FLAC、AAC；实际编码能力由 FFmpeg 决定。使用 `--help` 查看预设、编解码器、尺寸、帧率、音频和硬件参数。不支持的硬件编码会给出错误及软件回退建议。
- BT 使用本机认证 aria2 RPC，可添加 Magnet / Torrent，查看文件、选择下载项、暂停、恢复、重试及删除。CLI 与 TUI 共用持久化状态。引擎在退出客户端后继续下载，使用 `Frees-Tools torrent shutdown` 保存会话并停止后台引擎。

删除下载任务默认保留文件；永久删除数据需要二次确认。自动化必须同时明确传入：

```console
Frees-Tools torrent remove TASK_ID --delete-data --yes
```

## TUI 使用

左侧导航包括仪表盘、下载、图片、视频、PDF、任务、设置和帮助。大终端显示 ASCII 标题，小窗口简化标题。`Tab` / `Shift+Tab` 切换焦点，方向键选择，`Enter` 确认，`Esc` 回首页或关闭弹窗，`F1` 帮助，`Ctrl+T` 任务中心，`Ctrl+Q` 退出。

文件浏览器可以进入目录、返回上级、粘贴路径、多选文件，并在已选列表上移、下移、移除。PDF 页也可以逐行添加路径和调整顺序。转换运行时可以切换页面；任务中心提供进度、结果、错误、取消和当前会话内重试。图片、PDF、视频不提供暂停；暂停 / 恢复属于下载功能。退出界面会取消本地转换任务；重启后历史仍可查看，但重新执行转换需重新提交。

## 配置、故障与开发

配置和任务记录放在系统用户目录，具体位置由 `doctor` 显示。`FREES_TOOLS_HOME` 可为测试或便携使用指定独立目录。

```console
Frees-Tools config show
Frees-Tools config set max_downloads 3
Frees-Tools config set image_format webp
```

命令不存在时先检查 pipx / uv 工具目录是否加入 PATH；缺引擎时参考 `doctor`；密码保护或损坏文件会报告明确错误；源文件与输出路径相同请改用新文件名。BT 下载依赖有效 Peer 和网络连通性，不能把缺少 Peer 等同于软件已完成下载。

```console
git clone https://github.com/Frees-Ling/Frees-Tools.git
cd Frees-Tools
uv sync --frozen
uv run Frees-Tools --help
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
```

测试采用自行生成的图片、PDF、短视频与本地 Torrent；外部引擎测试在引擎可用时执行。详细证据与平台限制见发布检查。项目代码采用 MIT；第三方依赖遵循各自许可证，见 [第三方说明](docs/THIRD_PARTY.md)。
