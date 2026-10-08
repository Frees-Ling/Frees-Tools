# 发布就绪检查

验证日期：2026-10-09（北京时间）。功能提交 `1d844a4caab7702a60f1fc4e4c75ceab5bdbb9a8`。

## 原生验证

[CI 37843013822](https://github.com/Frees-Ling/Frees-Tools/actions/runs/37843013822) 实际执行四个平台的 Ruff、pytest、两个入口、JSON doctor、Wheel / sdist 和 PyInstaller 原生打包；封装程序另外启动并实际处理中文路径图片、PDF、短视频，执行响应式 TUI 自测及 aria2 启停。不是交叉编译或改名产物。

| 平台 | 源码回归 | 原生包 |
| --- | --- | --- |
| Windows x64 | 75 passed | `Frees-Tools-v0.1.0-windows-x64.zip` |
| macOS arm64 | 75 passed | `Frees-Tools-v0.1.0-macos-arm64.tar.gz` |
| macOS Intel x64 | 75 passed | `Frees-Tools-v0.1.0-macos-x64.tar.gz` |
| Linux x64 / Ubuntu 22.04 | 74 passed, 1 skipped | `Frees-Tools-v0.1.0-linux-x64.tar.gz` |

Linux 的跳过项仅适用于大小写不敏感文件系统；该项在 Windows 与 macOS 实际执行。所有四个平台都安装真实 FFmpeg / aria2，引擎集成未作为缺依赖跳过。本机另有 75 项通过与实际用户级 Wheel 安装验证。

PyInstaller 在 macOS / Linux 分析时提示找不到 Windows 专用 `shell32` / `ole32` 库；程序运行检查通过。这些诊断未被当作零警告或跨平台运行证明。

## 发布状态

- Python Wheel / sdist：已实际生成，命令入口与安装通过。
- 四个原生包：已各自在对应系统构建并运行检查。
- GitHub Release：待版本 Tag 工作流全部验证后创建；尚不据本文宣称发布成功。
- 校验值：本机构建生成 SHA256；Release 工作流汇总实际上传资产为 `SHA256SUMS`。
- PyPI：未发布。名称查询曾为 404；名称未保留，Trusted Publisher 与 GitHub `pypi` environment 未配置。恢复步骤见 `BUILD.md`。
- 签名 / 公证：没有项目正式证书，不宣称正式签名、公证或 SmartScreen 信誉。
- 外部引擎：FFmpeg / ffprobe / aria2 不随包提供，使用可信软件管理器安装；图片与 PDF 可直接使用。

## 已知边界

- Linux 原生基线 Ubuntu 22.04 / glibc 2.35；旧 glibc、musl 与额外 CPU 架构未保证。
- 当前界面简体中文，未来 i18n 已预留；AVIF / HEIC 不在首版保证范围。
- 多帧图片转换需显式选择第一帧；PDF 合成包含全部图片帧。加密 PDF 需先解除密码。
- 转换不覆盖输入，包括硬链接和大小写别名；目标覆盖需明确请求。多文件批量过程中取消可能保留已成功的独立结果。
- 本地转换退出会取消并清理未完成输出；当前会话可重试，跨重启需重新提交转换。下载历史和恢复状态持久化，客户端退出后后台继续；显式 `torrent shutdown` 保存并停止。
- 公共 Magnet 依赖实际网络与 Peer；测试证明本地真实协议传输，不能保证任意公共链接完成。
- 下载添加时已有目标文件或续传控制文件，不允许自动删除这些数据。Magnet 使用新建独立子目录；Torrent 预检异常路径与符号链接。
- 硬件编码依安装 FFmpeg 与设备；不可用时解释原因并提供软件回退建议。
