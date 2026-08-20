"""Flask 应用工厂：创建并配置 Web 服务。

对应文档「服务层」：
以 Flask 为核心，开发 Web 服务与 RESTful API 接口，返回标准化 JSON。
"""
from flask import Flask
from flask_cors import CORS


def create_app() -> Flask:
    """创建 Flask 应用实例（应用工厂模式，便于测试与扩展）。"""
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False  # 返回中文不转义
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    # 跨域：允许前端 Vite 开发服务器 (http://localhost:5173) 访问
    CORS(app)

    # 注册 API 蓝图
    from app.service_layer.api.routes import api
    app.register_blueprint(api)

    @app.errorhandler(404)
    def not_found(_error):
        from app.common.response import fail
        return fail("接口不存在", code=404), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        from app.common.response import fail
        return fail("请求方法不允许", code=405), 405

    return app
