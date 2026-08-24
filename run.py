"""后端服务入口。

用法：
    python run.py
默认监听 http://127.0.0.1:5000，可通过 .env 中的 FLASK_HOST/FLASK_PORT 修改。
"""
from app.service_layer.app import create_app
from config import FLASK_CONFIG

app = create_app()

if __name__ == "__main__":
    app.run(
        host=FLASK_CONFIG["host"],
        port=FLASK_CONFIG["port"],
        debug=FLASK_CONFIG["debug"],
    )
