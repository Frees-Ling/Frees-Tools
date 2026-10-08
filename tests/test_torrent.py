import hashlib
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
import shutil
import threading
import time

import pytest

from frees_tools.core.errors import ToolError
from frees_tools.services import torrent


def encode(value):
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, str):
        return encode(value.encode())
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, list):
        return b"l" + b"".join(encode(x) for x in value) + b"e"
    return b"d" + b"".join(encode(k) + encode(value[k]) for k in sorted(value)) + b"e"


def test_unsafe_metadata():
    for name in ["../outside", "..", "/absolute", "C:evil", "bad\\name"]:
        with pytest.raises(ToolError, match="不安全"):
            torrent._validate_torrent(encode({b"info": {b"name": name}}))
    with pytest.raises(ToolError):
        torrent._validate_torrent(b"not a torrent")


@pytest.fixture
def service(tmp_path, monkeypatch):
    if not shutil.which("aria2c"):
        pytest.skip("aria2 integration requires installed engine")
    original = torrent.config.load_config
    monkeypatch.setattr(torrent.config, "load_config", lambda: {**original(), "torrent_dht": False})
    result = torrent.TorrentService(tmp_path / "state")
    yield result
    if result.runtime_path.exists():
        result.shutdown()


def test_real_rpc_pause_resume_reconnect(service, tmp_path):
    source = "magnet:?xt=urn:btih:" + "a" * 40
    first = service.add(source, tmp_path / "中文 下载")
    id = first["id"]
    assert service.pause(id)["status"] == "PAUSED"
    other = torrent.TorrentService(service.directory.parent)
    assert other.status(id)["status"] == "PAUSED"
    assert other.runtime["pid"] == service.runtime["pid"]
    service.shutdown()
    assert service.status(id)["status"] == "PAUSED"
    assert service.resume(id)["status"] in ("RUNNING", "PENDING")
    with pytest.raises(ToolError, match="确认"):
        service.remove(id, delete_data=True)
    assert service.remove(id)["status"] == "CANCELLED"
    assert service.list()[0]["id"] == id
    assert (
        service.runtime_path.stat().st_mode & 0o077 == 0 if __import__("os").name != "nt" else True
    )


def test_real_local_torrent_download(service, tmp_path):
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    data = b"Frees Tools legal local integration fixture\n" * 200
    (seed_dir / "fixture.bin").write_bytes(data)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(seed_dir)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        metainfo = {
            b"info": {
                b"name": b"fixture.bin",
                b"length": len(data),
                b"piece length": 16384,
                b"pieces": hashlib.sha1(data).digest(),
            },
            b"url-list": f"http://127.0.0.1:{server.server_port}/fixture.bin",
        }
        path = tmp_path / "local.torrent"
        path.write_bytes(encode(metainfo))
        task = service.add(path, tmp_path / "result")
        deadline = time.monotonic() + 20
        while task["status"] not in ("COMPLETED", "FAILED") and time.monotonic() < deadline:
            time.sleep(0.2)
            task = service.status(task["id"])
        assert task["status"] == "COMPLETED", task
        assert (tmp_path / "result" / "fixture.bin").read_bytes() == data
        assert task["progress"] == 100
        service.shutdown()
        # Completed records survive daemon restart and absent engine result history.
        assert service.status(task["id"])["status"] == "COMPLETED"
        service.remove(task["id"], delete_data=True, confirm=True)
        assert not (tmp_path / "result" / "fixture.bin").exists()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_real_magnet_metadata_and_content(service, tmp_path):
    """Real BitTorrent metadata exchange and piece transfer, entirely over loopback."""
    from http.server import BaseHTTPRequestHandler
    import socket
    import struct
    import subprocess
    from urllib.parse import parse_qs, urlparse, quote

    peers = set()

    class Tracker(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            port = int(query.get("port", ["0"])[0])
            if port:
                peers.add(port)
            compact = b"".join(
                socket.inet_aton("127.0.0.1") + struct.pack("!H", p) for p in peers if p != port
            )
            body = encode({b"interval": 1, b"complete": 1, b"incomplete": 0, b"peers": compact})
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    tracker = ThreadingHTTPServer(("127.0.0.1", 0), Tracker)
    worker = threading.Thread(target=tracker.serve_forever, daemon=True)
    worker.start()
    seed_dir = tmp_path / "seeder"
    seed_dir.mkdir()
    data = b"Frees Tools local magnet protocol fixture\n" * 300
    (seed_dir / "magnet.bin").write_bytes(data)
    metadata = {
        b"name": b"magnet.bin",
        b"length": len(data),
        b"piece length": 16384,
        b"pieces": hashlib.sha1(data).digest(),
    }
    tracker_url = f"http://127.0.0.1:{tracker.server_port}/announce"
    path = tmp_path / "seed.torrent"
    path.write_bytes(encode({b"info": metadata, b"announce": tracker_url}))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        seed_port = probe.getsockname()[1]
    seeder = subprocess.Popen(
        [
            str(torrent.find_engine("aria2c")),
            "--enable-dht=false",
            "--enable-dht6=false",
            "--bt-enable-lpd=false",
            "--disable-ipv6=true",
            "--seed-time=2",
            "--check-integrity=true",
            "--bt-tracker-interval=1",
            "--listen-port=" + str(seed_port),
            "--dir=" + str(seed_dir),
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while seed_port not in peers and time.monotonic() < deadline:
            time.sleep(0.1)
        assert seed_port in peers, "Local seeder failed to announce"
        magnet = (
            "magnet:?xt=urn:btih:"
            + hashlib.sha1(encode(metadata)).hexdigest()
            + "&tr="
            + quote(tracker_url, safe="")
        )
        task = service.add(magnet, tmp_path / "magnet-result")
        deadline = time.monotonic() + 30
        while task["status"] not in ("COMPLETED", "FAILED") and time.monotonic() < deadline:
            time.sleep(0.2)
            task = service.status(task["id"])
        assert task["status"] == "COMPLETED", task
        assert (Path(task["directory"]) / "magnet.bin").read_bytes() == data
        assert task["engine_id"] != task["id"], "Must follow metadata task to content task"
    finally:
        seeder.terminate()
        try:
            seeder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            seeder.kill()
            seeder.wait(timeout=5)
        tracker.shutdown()
        tracker.server_close()
        worker.join(timeout=2)
