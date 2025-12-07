"""
控制面板 - 提供只读/有限控制的 Web 接口

设计目标：
- 仅使用标准库 wsgiref/simple_server，减少攻击面
- 支持简单的 Bearer Token 认证
- 可选开启 HTTPS（需提供证书/私钥）
- 所有接口均返回 JSON，避免模板引擎和额外依赖
"""
import json
import ssl
import threading
from typing import Any, Dict, Callable
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler


class ControlPanel:
    """轻量级控制面板"""

    def __init__(
        self,
        monitor_service,
        host: str,
        port: int,
        auth_token: str,
        enable_https: bool = False,
        certfile: str = "",
        keyfile: str = "",
    ):
        self.monitor = monitor_service
        self.host = host
        self.port = port
        self.auth_token = auth_token or ""
        self.enable_https = enable_https
        self.certfile = certfile
        self.keyfile = keyfile

        self._server = None  # type: ignore
        self._thread = None  # type: ignore

    # ------------------- WSGI 应用 -------------------
    def _app(self, environ, start_response: Callable):
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET").upper()

        try:
            # 健康检查允许匿名访问
            if path == "/health" and method == "GET":
                ok = self.monitor.health_check()
                return self._json(start_response, 200 if ok else 503, {"status": "ok" if ok else "fail"})

            # 其余接口需要认证
            if not self._is_authorized(environ):
                return self._json(start_response, 401, {"error": "unauthorized"})

            if path == "/status" and method == "GET":
                return self._json(start_response, 200, self._status_payload())

            if path == "/run_once" and method == "POST":
                self.monitor.run_check_cycle()
                return self._json(start_response, 200, {"message": "check cycle finished"})

            if path == "/config" and method == "GET":
                return self._json(start_response, 200, self._config_payload())

            return self._json(start_response, 404, {"error": "not found"})
        except Exception as exc:
            return self._json(start_response, 500, {"error": str(exc)})

    def _is_authorized(self, environ) -> bool:
        if not self.auth_token:
            return True
        auth_header = environ.get("HTTP_AUTHORIZATION", "")
        prefix = "Bearer "
        if auth_header.startswith(prefix):
            token = auth_header[len(prefix) :].strip()
            return token == self.auth_token
        return False

    def _json(self, start_response: Callable, code: int, payload: Dict[str, Any]):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(
            f"{code} OK",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(data))),
            ],
        )
        return [data]

    def _status_payload(self) -> Dict[str, Any]:
        return {
            "running": self.monitor.running,
            "start_time": getattr(self.monitor, "start_time", None).isoformat() if getattr(self.monitor, "start_time", None) else None,
            "last_cycle_started": getattr(self.monitor, "last_cycle_started", None).isoformat() if getattr(self.monitor, "last_cycle_started", None) else None,
            "last_cycle_finished": getattr(self.monitor, "last_cycle_finished", None).isoformat() if getattr(self.monitor, "last_cycle_finished", None) else None,
            "targets": len(self.monitor.config.get("targets", [])),
            "inactive_days_threshold": self.monitor.config.get("check_config", {}).get("inactive_days_threshold"),
        }

    def _config_payload(self) -> Dict[str, Any]:
        # 仅返回非敏感概要信息
        check_cfg = self.monitor.config.get("check_config", {})
        email_cfg = self.monitor.config.get("email", {})
        return {
            "check_interval_hours": check_cfg.get("check_interval_hours"),
            "inactive_days_threshold": check_cfg.get("inactive_days_threshold"),
            "email_sender": email_cfg.get("sender_email"),
            "email_receiver": email_cfg.get("receiver_email"),
        }

    # ------------------- 生命周期 -------------------
    def start(self):
        if self._server:
            return

        def server_factory(*args, **kwargs):
            httpd = make_server(self.host, self.port, self._app, *args, **kwargs)
            if self.enable_https:
                if not self.certfile or not self.keyfile:
                    raise ValueError("启用 HTTPS 时必须提供 certfile 与 keyfile")
                httpd.socket = ssl.wrap_socket(
                    httpd.socket,
                    server_side=True,
                    certfile=self.certfile,
                    keyfile=self.keyfile,
                    ssl_version=ssl.PROTOCOL_TLS_SERVER,
                )
            return httpd

        self._server = server_factory()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

