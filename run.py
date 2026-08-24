"""后端服务入口。

用法：
    python run.py
默认监听 http://127.0.0.1:5000，可通过 .env 中的 FLASK_HOST/FLASK_PORT 修改。
"""
import socket

from app.service_layer.app import create_app
from config import FLASK_CONFIG

app = create_app()


def ensure_port_available(host: str, port: int) -> None:
    """防止 Windows 上多个 Flask 开发服务器复用同一端口。

    多实例会让浏览器请求随机落到旧代码，因此启动前直接拒绝已被监听的端口。
    """
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    try:
        with socket.create_connection((probe_host, int(port)), timeout=0.5):
            pass
    except OSError:
        return
    raise SystemExit(
        f"无法启动后端：{host}:{port} 已有服务在监听。"
        "请复用已启动的服务，或先关闭旧进程。"
    )


if __name__ == "__main__":
    ensure_port_available(FLASK_CONFIG["host"], FLASK_CONFIG["port"])
    app.run(
        host=FLASK_CONFIG["host"],
        port=FLASK_CONFIG["port"],
        debug=FLASK_CONFIG["debug"],
    )
