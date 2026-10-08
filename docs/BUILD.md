# 开发、构建与发布

## 本地开发

```console
git clone https://github.com/Frees-Ling/Frees-Tools.git
cd Frees-Tools
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run Frees-Tools --version
uv run frees-tools --help
uv build
```

依赖由 `pyproject.toml` 与 `uv.lock` 管理。Wheel 与源码包位于 `dist/`。测试包含真实图片 / PDF 文件、TUI Pilot、CLI，以及引擎存在时执行的本地集成测试。查看 pytest 的 skip 原因；跳过的测试不代表通过。公共网络条件与本地 Torrent 传输应分别记录。

隔离测试配置可设置 `FREES_TOOLS_HOME` 到临时目录；不要在真实下载实例仍运行时删除其配置 / 状态目录。默认测试使用自建素材，不要求下载第三方版权内容。

## 原生打包

```console
uv run python scripts/build_release.py
```

脚本只打包当前操作系统和架构，使用 PyInstaller onedir，随后启动产物验证版本、帮助、JSON doctor，并处理真实中文路径图片与 PDF。保留整个输出目录。Windows 输出 ZIP，macOS / Linux 输出 tar.gz；旁边生成 SHA256 校验文件。项目代码和第三方说明随包附带；FFmpeg / aria2 不随包。

计划资产命名：

| 平台 | 资产 |
| --- | --- |
| Windows x64 | `Frees-Tools-v0.1.0-windows-x64.zip` |
| macOS Apple Silicon | `Frees-Tools-v0.1.0-macos-arm64.tar.gz` |
| macOS Intel | `Frees-Tools-v0.1.0-macos-x64.tar.gz` |
| Linux x64 | `Frees-Tools-v0.1.0-linux-x64.tar.gz` |

这是命名约定，不是已经产生全部资产的声明。Linux 使用 Ubuntu 22.04、glibc 2.35 构建基线；旧 glibc / musl 未保证。macOS 和 Windows 暂无正式签名 / 公证，必须如实告知用户。

## GitHub Actions

`ci.yml` 在 push / PR 时执行平台矩阵检查；`release.yml` 在 `v*` Tag 或手动触发时测试和构建 Windows、Linux、macOS arm64 / Intel。只有全部构建任务成功，Tag 触发的发布任务才会创建 GitHub Release、上传资产与汇总 SHA256SUMS。手动触发用于验证构建，不自动当作正式 Tag 发布。

工作流使用只读默认权限，只有实际 Release 写入步骤获得 `contents: write`。不要给不可信 PR 提供仓库写入或发布凭据。Runner 标签与账户权限属于外部前提；核对实际执行结果，不以 YAML 存在代替平台验证。

正式发布前：完成 `docs/RELEASE_READINESS.md` 所有阻断项，核对版本、CHANGELOG、发行说明、真实平台测试、压缩包内容、校验值和 CLI 两种入口。然后使用普通提交和版本 Tag，不强推、不覆盖已有版本。若 GitHub 权限不足，保留本地产物并记录错误，不宣称已发布。

## PyPI Trusted Publishing

PyPI 项目尚未发布。名称查询曾返回 404 只表示当时没有可见项目，不表示名称已保留，也不证明账户授权。

1. 在 PyPI 账户中创建与仓库对应的 pending publisher / trusted publisher，项目名 `frees-tools`，仓库所有者 `Frees-Ling`，仓库 `Frees-Tools`，工作流 `pypi.yml`，环境 `pypi`。
2. 在 GitHub 创建 `pypi` environment，配置受保护分支和人工审核人。
3. 检查实际构建版本与已有版本不冲突，先完成全部发布验证。
4. 手动触发 `.github/workflows/pypi.yml`。发布阶段使用 OIDC 的 `id-token: write`，不保存 PyPI Token 到源码。
5. 核验 PyPI 项目记录和安装结果后才更新“已发布”状态。

授权未设置或名称冲突时不得执行成功声明；可继续分发已核验 Wheel / 原生包及 Git 源码安装。Trusted Publishing 准备完毕不等于已成功上传。
