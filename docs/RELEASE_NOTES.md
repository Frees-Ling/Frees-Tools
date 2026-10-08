# Frees Tools v0.1.0

图片转换、PDF 合成、FFmpeg 视频处理和 aria2 BitTorrent 下载，统一提供 Textual 界面与 CLI。运行 `Frees-Tools` 或 `frees-tools` 启动交互界面；`--help` 查看命令，`doctor` 检查环境，`--json` 输出机器可读结果。

## 资产与安装

选择匹配操作系统和 CPU 的压缩包，解压整个目录，对照 `SHA256SUMS` 校验后运行主程序。压缩包无需另装 Python。Windows 为 ZIP；macOS / Linux 为 tar.gz。保留主程序旁的依赖目录，加入 PATH 后可从任意工作目录启动。

Python 用户可安装附件 Wheel，或使用：

```console
pipx install git+https://github.com/Frees-Ling/Frees-Tools.git
```

PyPI 授权与上传结果必须单独核验；本说明不声明已经发布 PyPI。

## 依赖与行为

FFmpeg / ffprobe 与 aria2c **不随包提供**；视频和下载功能需先通过可信系统软件管理器安装。图片 / PDF 使用包内 Python 依赖。安装指导见随包 `INSTALL.md`，第三方许可证见随包声明与许可证目录。

- 图片多帧输入需显式选择仅第一帧；PDF 接收图片全部帧。
- 输出默认不覆盖，`--overwrite` 也不能覆盖输入源文件。
- 本地转换退出后取消；下载引擎在客户端退出后继续运行，使用 `torrent shutdown` 保存会话并停止。
- 删除下载任务默认保留数据；删除数据需要额外确认。
- 已完成和失败历史会保留；跨重启转换重试需重新提交。

## 平台限制

macOS / Windows 暂未进行正式代码签名或公证，系统可能提示未知发布者。核验来源，不要关闭全局安全保护。Linux 构建基线为 Ubuntu 22.04 / glibc 2.35，未保证旧 glibc / Alpine musl。硬件编码及具体编解码器依安装的 FFmpeg 能力而定。公共 Magnet 下载依实际网络与 Peer 条件，不能保证任意链接有可用资源。

本版已在 Windows x64、macOS arm64、macOS Intel x64、Ubuntu 22.04 x64 实际测试并构建，各平台封装程序通过启动和真实业务冒烟。源码回归 Windows / macOS 各 75 项通过，Linux 74 项通过、1 项跳过（仅适用大小写不敏感文件系统）。详细证据和边界见仓库 `docs/RELEASE_READINESS.md`。
