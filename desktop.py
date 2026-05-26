from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import uvicorn

from app.main import app


APP_TITLE = "意图驱动跨域网络自治系统"


def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("本地服务启动超时")


def log_path() -> Path:
    return Path.cwd() / "desktop.log"


def main() -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("缺少 pywebview，请先安装依赖：pip install -r requirements.txt") from exc

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        wait_until_ready(url)
        window = webview.create_window(APP_TITLE, url, width=1280, height=860, min_size=(980, 680))

        def on_closed() -> None:
            server.should_exit = True

        window.events.closed += on_closed
        webview.start(debug=False)
    except Exception as exc:
        log_path().write_text(str(exc), encoding="utf-8")
        raise
    finally:
        server.should_exit = True
        thread.join(timeout=3)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_path().write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        sys.exit(1)
