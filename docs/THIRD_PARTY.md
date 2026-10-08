# 第三方组件与发行边界

Frees Tools 项目代码采用仓库 `LICENSE` 中的 MIT 许可证。该许可证不替代依赖库、编解码器、外部引擎和打包工具的许可证。发行时必须保留所用版本的版权和许可证文本，不能仅凭本页摘要宣称满足全部义务。

## Python 组件

以下摘要来自本次开发环境的已安装包元数据；最终依赖及版本以 `uv.lock` 和实际构建产物为准。

| 组件 | 用途 | 许可证摘要 |
| --- | --- | --- |
| Textual | TUI | MIT |
| Rich | 终端输出 | MIT |
| Typer | CLI | MIT |
| Pillow | 图片处理、图片 PDF 编码 | MIT-CMU |
| pypdf | PDF 读取与合并 | BSD-3-Clause |
| platformdirs | 用户配置与状态目录 | MIT |
| PyInstaller | 独立程序打包 | GPLv2-or-later，附专用分发例外 |

Textual 等组件还会引入传递依赖，Pillow 二进制 Wheel 也可能包含独立图像编解码库。检查各安装包 `.dist-info/licenses`、`LICENSE*`、`COPYING*` 及构建工具收集结果。最终发行包应附完整第三方许可证目录，保留声明和需要提供的源代码信息；本表不能替代逐版本检查。

PyInstaller 的例外允许按应用自身许可证分发生成程序，但仍须遵守依赖许可证。详见 [PyInstaller 官方许可说明](https://pyinstaller.org/en/stable/license.html)。本项目未修改其工具源码。PDF 服务使用 Pillow 与 pypdf，不需要 img2pdf。

## FFmpeg 与 aria2

首版发行包**不附带 FFmpeg、ffprobe、aria2c 可执行文件**。用户主动通过可信操作系统软件管理器安装，Frees Tools 只发现并调用已安装程序。软件不自动下载外部可执行文件。

FFmpeg 的许可依编译配置、启用库和版本而不同，不能笼统认为所有二进制都采用同一许可证，见 [FFmpeg 官方许可说明](https://ffmpeg.org/legal.html)。aria2 也有自身许可证和源码义务，见 [aria2 COPYING](https://github.com/aria2/aria2/blob/master/COPYING)。未来随包提供这些引擎前，必须记录确切版本、可信来源、SHA256、构建选项、许可证全文及适用源码提供方式；未完成审计不得加入资产。

系统安装使用的软件管理器及第三方二进制发布方不是本项目维护方。用户可查看 `doctor` 输出中的程序路径和版本，以及引擎自身许可证信息。项目没有对受专利约束的编解码器提供额外授权保证。

## 发布检查

构建后核对压缩包中的项目 LICENSE、第三方声明和完整依赖许可证；核对实际包含的库而非只看直接依赖。任何缺失声明或未处理的源码义务属于发布阻断项。具体审计证据见 `docs/RELEASE_READINESS.md`。

## 对应源码与上游入口

精确版本可从 `uv.lock` 和原生包中的依赖元数据核对；在上游仓库选择对应版本的 Tag 后查阅许可证和源码。

- [Textual 源码](https://github.com/Textualize/textual)
- [Rich 源码](https://github.com/Textualize/rich)
- [Typer 源码](https://github.com/fastapi/typer)
- [Pillow 源码](https://github.com/python-pillow/Pillow)
- [pypdf 源码](https://github.com/py-pdf/pypdf)
- [platformdirs 源码](https://github.com/tox-dev/platformdirs)
- [PyInstaller 源码及例外全文](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)

从源码构建时执行 `uv sync --frozen` 安装锁定版本。原生包应保留自动收集的 `licenses/` 目录，包括 Python 标准运行时和传递依赖声明；以实际资产中的目录为准。
