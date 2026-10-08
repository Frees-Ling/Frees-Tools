# 参与开发

欢迎提交错误复现、文档修正和维护性改进。请先阅读 README 与 `docs/ARCHITECTURE.md`，避免在 CLI / TUI 重复实现服务。

## 本地检查

Python 3.11+；推荐 uv。

```console
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

需要修改格式时运行 `uv run ruff format .`。外部引擎集成测试要求 ffmpeg、ffprobe、aria2c；查看跳过原因并在 PR 中说明没有执行的测试。测试应使用自行生成或明确授权的小型合法素材，公共网络测试必须与默认离线测试分离。

## 提交要求

一个改动说明一个具体问题，解释最终行为、验证方法及实际限制。新业务逻辑放入 services；支持取消和真实进度；跨平台路径使用 Path，外部进程使用参数数组。保留源文件，覆盖需明确授权，失败不能发布半成品。新增依赖需要说明体积、许可证和冻结构建影响。

界面改动请运行 Textual Pilot 测试并实际检查键盘焦点、小窗口和错误展示。跨平台声明须有对应平台证据；本地通过不等于全平台通过。不要提交下载数据、用户配置、RPC 凭据、日志中的敏感信息或构建缓存。

安全问题遵循 `SECURITY.md`。只有所有发布阻断项解决后才允许正式发布；没有权限的贡献者提交 PR，维护者按正常流程合并，不强推共享分支。
