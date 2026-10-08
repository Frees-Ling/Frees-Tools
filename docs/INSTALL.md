# 安装与使用手册

## 选择安装方式

源码安装要求 Python 3.11+，独立发行包不要求另装 Python。当前是否已经发布、哪些平台已有测试证据，请先查看仓库的 `docs/RELEASE_READINESS.md` 和 GitHub Releases。PyPI 尚未发布，不要将同名第三方包视为本项目。

已安装 pipx 时：

```console
pipx install git+https://github.com/Frees-Ling/Frees-Tools.git
pipx ensurepath
```

已安装 uv 时：

```console
uv tool install git+https://github.com/Frees-Ling/Frees-Tools.git
uv tool update-shell
```

重新打开终端后，两个命令均可使用：

```console
Frees-Tools --version
frees-tools --help
Frees-Tools
```

从本地仓库安装可执行 `uv tool install .`。开发模式使用 `uv sync --frozen` 与 `uv run Frees-Tools`。通过 pipx 从 Git 安装的用户可用 `pipx upgrade frees-tools` 更新；通过 uv 安装的用户可用 `uv tool upgrade frees-tools` 更新。更新前保留正在处理的文件并停止本地转换。

## 独立发行包

从项目 GitHub Releases 选择与操作系统、CPU 匹配的资产；不要混用 arm64 与 x64。下载包后对照随发行版提供的 SHA256SUMS 校验。macOS 可用 `shasum -a 256 文件名`，Linux 可用 `sha256sum 文件名`，Windows PowerShell 可用 `Get-FileHash 文件名 -Algorithm SHA256`。

解压整个 `Frees-Tools` 目录，保留内部依赖目录。Windows 启动 `Frees-Tools.exe`，PowerShell 使用 `./Frees-Tools.exe`；macOS / Linux 在目录中使用 `./Frees-Tools`。要在任意工作目录使用，将整个解压目录加入用户 PATH，再重新打开终端。不要只复制主程序。

macOS 与 Windows 发行包目前没有项目维护者正式代码签名或公证。macOS 可能要求在“系统设置 → 隐私与安全性”核准来自已核验来源的应用；Windows 可能显示未知发布者提示。先核验来源及校验值，保留系统安全保护，不要为安装关闭全局防护。

Linux 原生包的构建基线为 Ubuntu 22.04 / glibc 2.35，不能保证在更旧 glibc 或 Alpine musl 上运行；这些系统可尝试符合 Python 依赖要求的源码安装。各平台实际构建结果以发布检查为准。

## 安装视频和下载引擎

FFmpeg、ffprobe、aria2c 不在发行包内。只用图片与 PDF 时无需安装外部引擎。

macOS，已有 Homebrew：

```console
brew install ffmpeg aria2
```

Ubuntu / Debian：

```console
sudo apt update
sudo apt install ffmpeg aria2
```

Windows，已有 winget：

```console
winget install Gyan.FFmpeg
winget install aria2.aria2
```

这些命令由用户主动执行；软件不会自动联网安装引擎。仓库不维护第三方安装包镜像。请查阅软件管理器显示的来源、版本和许可证。

安装后重新打开终端：

```console
Frees-Tools doctor
Frees-Tools --json doctor
```

优先查找发行包内部引擎、用户配置路径、系统 PATH；每个候选会执行版本校验。高级用户可以设置显式路径：

```console
Frees-Tools config set engines '{"ffmpeg":"/absolute/path/ffmpeg","ffprobe":"/absolute/path/ffprobe","aria2c":"/absolute/path/aria2c"}'
```

Windows PowerShell 的 JSON 引号规则可能因版本不同；可打开用户配置目录中的 `config.json` 修改 `engines` 对象，Windows 路径中的反斜杠按 JSON 要求转义。`doctor` 显示实际配置目录及最终引擎路径。

## 界面操作

启动后左侧选择模块。使用 Tab / Shift+Tab、方向键、Enter 操作；Esc 回首页或关闭弹窗，F1 帮助，Ctrl+T 任务中心，Ctrl+Q 退出。

文件选择不是系统图形弹窗，而是终端文件浏览器。输入路径后按 Enter 打开目录或文件；选定文件会加入列表，可调整顺序和移除，最后点击“使用选择”。目录模式支持选择当前目录。PDF 按已选列表顺序合成；可逐行输入路径、上移、下移。带空格路径直接粘贴到输入框，无需添加 shell 引号。

开始转换后切换页面不会中止任务。任务中心显示进度、结果及错误详情；取消需确认。当前会话内可以重试，重启后请在工具页重新提交。退出时本地图片、PDF、视频转换会取消，完成前临时文件会清理；源文件保留。BT 引擎继续后台下载，需主动运行 `Frees-Tools torrent shutdown` 停止。

## 参数与数据

图片宽高为保持比例的边界；缩放百分比与宽高不可同时使用。GIF / TIFF 多帧转换需明确选择仅第一帧；PDF 会接收全部帧。PDF `contain` 完整显示，`cover` 铺满裁切；`auto` 保留 PDF 页面尺寸、按 96 DPI 创建图片页。PDF 密码需在外部先解除。

视频转换要求显式输出路径。先用 `video info` 查看输入，再用 `video convert --help` 查看本版本参数。不支持的编码器或硬件会给出错误，移除硬件请求后可使用软件编码；首版没有承诺所有设备硬件加速可用。

下载文件选择使用 aria2 的一基索引，如 `--select-files "1,3"`。Magnet 元数据获取需要网络和 Peer，文件列表在元数据可用后才有意义。暂停不删除文件；删除任务默认保留数据。永久删除必须确认或明确指定 `--delete-data --yes`。

配置和状态保存在平台用户目录；`config show` 显示配置，`doctor` 显示位置。异常配置会保留 `.invalid.json` 备份并使用默认值。需要独立环境时，在启动进程前设置 `FREES_TOOLS_HOME`；切换该目录意味着使用另一组任务和后台引擎状态，不能指望连接原目录的后台实例。

## 常见问题

- 命令不存在：重新打开终端并检查 pipx / uv 工具目录或解压目录是否在 PATH。
- 非交互环境只有帮助：属于预期行为；使用明确子命令，或在交互式终端启动界面。
- 引擎缺失：运行 `doctor`，安装后重开终端，必要时配置绝对路径。
- 输出已存在：改名或明确使用 `--overwrite`。输出不得与源文件同路径。
- 图片多帧错误：只有接受舍弃其他帧时才加 `--first-frame`；要全部保存为 PDF 使用 `pdf from-images`。
- 下载等待：查看 `torrent status` 中状态、Peer、错误信息，检查 Tracker / DHT / 网络；无 Peer 不能保证下载完成。
- PDF 加密、空文件或损坏：修复或解密源文件后重试；转换器不会猜测密码。
- 终端太小：扩大窗口，或使用 CLI；ASCII 标题会自动简化。

删除下载数据的额外保护：种子任务添加时若目标文件已存在，程序拒绝自动删除这些数据；磁力任务会在指定目录内创建独立的 Frees-Tools-* 子目录，防止元数据通过既有符号链接写到目录之外。此时仍可移除任务并保留文件，再手动核对目录。新建独立下载目录可明确数据归属。
