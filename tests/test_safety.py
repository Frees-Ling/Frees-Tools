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
    assert list(tmp_path.iterdir()) == [tmp_path / "config.json"]
