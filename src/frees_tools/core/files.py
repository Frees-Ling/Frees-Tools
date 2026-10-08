"""Safe output publication: protect sources and commit only complete files."""

from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
from .errors import ToolError


@contextmanager
def output_file(destination, sources=(), overwrite=False):
    target = Path(destination).expanduser().resolve()
    if target in {Path(p).expanduser().resolve() for p in sources}:
        raise ToolError("输出路径不能与源文件相同。请选择新的文件名。")
    if target.exists() and not overwrite:
        raise ToolError(f"输出已存在：{target}；使用 --overwrite 明确覆盖。")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".frees-tools-", suffix=target.suffix, dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise ToolError("处理未生成有效输出。")
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise ToolError(f"输出已存在：{target}") from exc
    finally:
        temporary.unlink(missing_ok=True)
