"""Focused regressions for preserving user data at service boundaries."""

import pytest
from PIL import Image

from frees_tools.core.errors import ToolError
from frees_tools.services import images, torrent


def bencode(value):
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    return b"d" + b"".join(bencode(k) + bencode(value[k]) for k in sorted(value)) + b"e"


def offline_service(tmp_path, monkeypatch):
    service = torrent.TorrentService(tmp_path / "state")
    calls = []
    monkeypatch.setattr(service, "_ensure_unlocked", lambda: None)

    def rpc(method, *args):
        calls.append(method)
        return "offline-id" if method in ("addTorrent", "addUri") else "OK"

    monkeypatch.setattr(service, "_rpc", rpc)
    monkeypatch.setattr(service, "status", lambda identity: service._records()[identity])
    return service, calls


def test_batch_never_overwrites_another_source(tmp_path):
    a, b = tmp_path / "same.jpg", tmp_path / "same.png"
    Image.new("RGB", (4, 4), "red").save(a)
    Image.new("RGB", (4, 4), "blue").save(b)
    originals = {path: path.read_bytes() for path in (a, b)}
    result = images.batch(tmp_path, "png", tmp_path, overwrite=True)
    assert result["failed"] == 2
    assert all(path.read_bytes() == data for path, data in originals.items())


@pytest.mark.parametrize("metadata", [{b"name": 42}, 42, {b"name": []}])
def test_torrent_invalid_schema_has_meaningful_error(metadata):
    with pytest.raises(ToolError):
        torrent._validate_torrent(bencode({b"info": metadata}))


def test_torrent_rejects_symlink_parent_before_rpc(tmp_path, monkeypatch):
    service, calls = offline_service(tmp_path, monkeypatch)
    destination, outside = tmp_path / "downloads", tmp_path / "outside"
    destination.mkdir()
    outside.mkdir()
    try:
        (destination / "bundle").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Creating directory symlinks requires platform privileges")
    source = tmp_path / "bundle.torrent"
    source.write_bytes(
        bencode({b"info": {b"name": b"bundle", b"files": [{b"path": [b"new.bin"], b"length": 1}]}})
    )
    with pytest.raises(ToolError):
        service.add(source, destination)
    assert "addTorrent" not in calls
    assert not (outside / "new.bin").exists()


def test_torrent_preexisting_file_disables_data_deletion(tmp_path, monkeypatch):
    service, _ = offline_service(tmp_path, monkeypatch)
    destination = tmp_path / "downloads"
    destination.mkdir()
    user_file = destination / "user.bin"
    user_file.write_bytes(b"original user data")
    source = tmp_path / "user.torrent"
    source.write_bytes(bencode({b"info": {b"name": b"user.bin", b"length": 18}}))
    record = service.add(source, destination)
    assert record["delete_data_allowed"] is False
    with pytest.raises(ToolError):
        service.remove(record["id"], delete_data=True, confirm=True)
    assert user_file.read_bytes() == b"original user data"


def test_torrent_preexisting_sidecar_disables_data_deletion(tmp_path, monkeypatch):
    service, _ = offline_service(tmp_path, monkeypatch)
    destination = tmp_path / "downloads"
    destination.mkdir()
    sidecar = destination / "user.bin.aria2"
    sidecar.write_bytes(b"preexisting resume data")
    source = tmp_path / "user.torrent"
    source.write_bytes(bencode({b"info": {b"name": b"user.bin", b"length": 18}}))
    record = service.add(source, destination)
    assert record["delete_data_allowed"] is False
    assert sidecar.read_bytes() == b"preexisting resume data"


def test_concurrent_config_saves_use_independent_temporary_files(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from frees_tools.core import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    workers = 8
    barrier = Barrier(workers)

    def save(index):
        barrier.wait(timeout=5)
        value = {**config.DEFAULTS, "max_downloads": index + 1}
        return config.save_config(value)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(save, range(workers)))
    assert len(results) == workers
    assert config.load_config()["max_downloads"] in range(1, workers + 1)
    assert {path.name for path in tmp_path.iterdir()} == {"config.json", ".config.lock"}


def test_output_rejects_hardlink_alias_of_source(tmp_path):
    from frees_tools.core.files import output_file

    source, alias = tmp_path / "source.png", tmp_path / "alias.png"
    source.write_bytes(b"original")
    try:
        alias.hardlink_to(source)
    except OSError:
        pytest.skip("Filesystem does not support hard links")
    with pytest.raises(ToolError):
        with output_file(alias, [source], overwrite=True):
            pytest.fail("A source alias must be rejected before opening a temporary file")
    assert source.read_bytes() == alias.read_bytes() == b"original"


def test_output_rejects_case_alias_on_case_insensitive_filesystem(tmp_path):
    from frees_tools.core.files import output_file

    source, alias = tmp_path / "original.png", tmp_path / "ORIGINAL.PNG"
    source.write_bytes(b"original")
    if not alias.exists():
        pytest.skip("Filesystem is case sensitive")
    with pytest.raises(ToolError):
        with output_file(alias, [source], overwrite=True):
            pytest.fail("A case alias must be rejected")
    assert source.read_bytes() == b"original"


def test_batch_protects_hardlink_alias_of_other_input(tmp_path):
    source_dir, output_dir = tmp_path / "source", tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()
    first, second = source_dir / "first.jpg", source_dir / "second.png"
    Image.new("RGB", (4, 4), "red").save(first)
    Image.new("RGB", (4, 4), "blue").save(second)
    alias = output_dir / "first.png"
    try:
        alias.hardlink_to(second)
    except OSError:
        pytest.skip("Filesystem does not support hard links")
    original = second.read_bytes()
    result = images.batch(source_dir, "png", output_dir, overwrite=True)
    assert result["failed"] == 1
    assert second.read_bytes() == alias.read_bytes() == original


def test_batch_casefold_collision_preserves_first_output(tmp_path):
    source_dir, output_dir = tmp_path / "source", tmp_path / "output"
    source_dir.mkdir()
    Image.new("RGB", (4, 4), "red").save(source_dir / "A.jpg")
    Image.new("RGB", (4, 4), "blue").save(source_dir / "a.png")
    result = images.batch(source_dir, "webp", output_dir, overwrite=True)
    assert result["completed"] == 1
    assert result["failed"] == 1
    assert "相同输出路径" in result["errors"][0]["error"]


def test_config_save_recovers_transient_replace_denial(tmp_path, monkeypatch):
    from pathlib import Path
    from frees_tools.core import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    original = Path.replace
    attempts = []

    def transient_replace(source, target):
        if source.name.startswith(".config-"):
            attempts.append(source)
            if len(attempts) < 3:
                raise PermissionError("transient Windows file sharing denial")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", transient_replace)
    config.save_config({**config.DEFAULTS, "max_downloads": 7})
    assert len(attempts) == 3
    assert config.load_config()["max_downloads"] == 7
    assert not list(tmp_path.glob(".config-*.tmp"))


def test_config_saves_across_processes(tmp_path):
    import os
    import subprocess
    import sys
    import json

    code = (
        "from frees_tools.core.config import save_config, DEFAULTS; "
        "import sys; "
        "[save_config({**DEFAULTS, 'max_downloads': int(sys.argv[1])}) for _ in range(12)]"
    )
    environment = {**os.environ, "FREES_TOOLS_HOME": str(tmp_path)}
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(index)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(1, 5)
    ]
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, (stdout, stderr)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert json.loads((tmp_path / "config.json").read_text())["max_downloads"] in range(1, 5)
    assert not list(tmp_path.glob(".config-*.tmp"))


def test_config_permanent_replace_denial_preserves_old_config(tmp_path, monkeypatch):
    from pathlib import Path
    from frees_tools.core import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    config.save_config({**config.DEFAULTS, "max_downloads": 2})
    original_bytes = (tmp_path / "config.json").read_bytes()
    attempts = []

    def denied_replace(source, target):
        attempts.append(source)
        raise PermissionError("persistent access denial")

    monkeypatch.setattr(Path, "replace", denied_replace)
    monkeypatch.setattr(config.time, "sleep", lambda seconds: None)
    with pytest.raises(PermissionError):
        config.save_config({**config.DEFAULTS, "max_downloads": 7})
    assert len(attempts) == 20
    assert (tmp_path / "config.json").read_bytes() == original_bytes
    assert not list(tmp_path.glob(".config-*.tmp"))
