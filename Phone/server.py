"""Standalone local server for the Phone chat web demo."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from Phone.facade import PhoneFacade

DEFAULT_COMPANION_ID = "cyrene"
DEFAULT_USER_ID = "user"
DEFAULT_TITLE = "昔涟"
DEFAULT_MESSAGE_LIMIT = 200
WEB_ROOT = Path(__file__).resolve().parent / "web"
COMPANION_DISPLAY_NAMES = {
    "cyrene": "昔涟",
}


class PhoneWebApplication:
    """Application layer for the standalone Phone browser experience."""

    def __init__(
        self,
        store_path: Optional[str] = None,
    ) -> None:
        self.facade = (
            PhoneFacade.from_store_path(store_path)
            if store_path is not None
            else PhoneFacade()
        )
        self.reply_backend = "tool"

    def bootstrap(
        self,
        companion_id: str = DEFAULT_COMPANION_ID,
        user_id: str = DEFAULT_USER_ID,
        title: str = DEFAULT_TITLE,
        limit: int = DEFAULT_MESSAGE_LIMIT,
    ) -> Dict[str, Any]:
        thread = self.facade.open_chat(
            companion_id=companion_id,
            user_id=user_id,
            title=title,
        )
        payload = self.facade.read_messages(thread.thread_id, limit=limit)
        return self._decorate_payload(payload)

    def read_messages(
        self,
        thread_id: str,
        limit: int = DEFAULT_MESSAGE_LIMIT,
    ) -> Dict[str, Any]:
        payload = self.facade.read_messages(thread_id=thread_id, limit=limit)
        return self._decorate_payload(payload)

    def post_message(
        self,
        thread_id: str,
        content: str,
        sender: str = "user",
        limit: int = DEFAULT_MESSAGE_LIMIT,
    ) -> Dict[str, Any]:
        normalized_sender = sender.strip().lower()
        if normalized_sender not in ("user", "companion"):
            raise ValueError("sender must be 'user' or 'companion'")

        if normalized_sender == "user":
            user_message = self.facade.send_from_user(thread_id=thread_id, content=content)
            payload = self.facade.read_messages(thread_id=thread_id, limit=limit)
            enriched = self._decorate_payload(payload)
            enriched["last_user_message"] = user_message.to_dict()
            return enriched

        companion_message = self.facade.send_from_companion(
            thread_id=thread_id,
            content=content,
        )
        payload = self.facade.read_messages(thread_id=thread_id, limit=limit)
        enriched = self._decorate_payload(payload)
        enriched["last_companion_message"] = companion_message.to_dict()
        return enriched

    def _decorate_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        thread = payload["thread"]
        companion_id = thread.get("companion_id", DEFAULT_COMPANION_ID)
        display_name = COMPANION_DISPLAY_NAMES.get(
            companion_id,
            thread.get("title") or companion_id,
        )
        return {
            "app": {
                "name": "Cybersoul Phone",
                "reply_backend": self.reply_backend,
                "tool_access_enabled": True,
                "auto_reply_enabled": False,
            },
            "companion": {
                "id": companion_id,
                "display_name": display_name,
            },
            **payload,
        }


class PhoneHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that carries the Phone application state."""

    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        app: PhoneWebApplication,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.app = app


class PhoneRequestHandler(BaseHTTPRequestHandler):
    """Serve the standalone Phone UI and its tiny JSON API."""

    server: PhoneHTTPServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path in ("/", "/index.html"):
                self._serve_static("index.html")
                return
            if parsed.path == "/styles.css":
                self._serve_static("styles.css")
                return
            if parsed.path == "/app.js":
                self._serve_static("app.js")
                return
            if parsed.path == "/api/health":
                self._json_response(HTTPStatus.OK, {"status": "ok"})
                return
            if parsed.path == "/api/bootstrap":
                params = parse_qs(parsed.query)
                payload = self.server.app.bootstrap(
                    companion_id=self._query_value(params, "companion_id", DEFAULT_COMPANION_ID),
                    user_id=self._query_value(params, "user_id", DEFAULT_USER_ID),
                    title=self._query_value(params, "title", DEFAULT_TITLE),
                    limit=self._query_int(params, "limit", DEFAULT_MESSAGE_LIMIT),
                )
                self._json_response(HTTPStatus.OK, payload)
                return
            if parsed.path == "/api/messages":
                params = parse_qs(parsed.query)
                thread_id = self._required_query_value(params, "thread_id")
                payload = self.server.app.read_messages(
                    thread_id=thread_id,
                    limit=self._query_int(params, "limit", DEFAULT_MESSAGE_LIMIT),
                )
                self._json_response(HTTPStatus.OK, payload)
                return
        except ValueError as exc:
            self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_request", "message": str(exc)},
            )
            return
        except Exception as exc:
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "server_error", "message": str(exc)},
            )
            return

        self._json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "not_found", "message": "请求的资源不存在。"},
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/messages":
                payload = self._read_json_body()
                response = self.server.app.post_message(
                    thread_id=self._required_value(payload, "thread_id"),
                    content=self._required_value(payload, "content"),
                    sender=str(payload.get("sender", "user")),
                    limit=int(payload.get("limit", DEFAULT_MESSAGE_LIMIT)),
                )
                self._json_response(HTTPStatus.OK, response)
                return
        except ValueError as exc:
            self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_request", "message": str(exc)},
            )
            return
        except Exception as exc:
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "server_error", "message": str(exc)},
            )
            return

        self._json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "not_found", "message": "请求的资源不存在。"},
        )

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _serve_static(self, filename: str) -> None:
        file_path = WEB_ROOT / filename
        if not file_path.is_file():
            self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": "静态资源不存在。"},
            )
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def _json_response(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query_value(
        self,
        params: Dict[str, list[str]],
        key: str,
        default: str,
    ) -> str:
        values = params.get(key)
        if not values or not values[0]:
            return default
        return values[0]

    def _required_query_value(
        self,
        params: Dict[str, list[str]],
        key: str,
    ) -> str:
        values = params.get(key)
        if not values or not values[0]:
            raise ValueError("missing required query parameter: " + key)
        return values[0]

    def _query_int(
        self,
        params: Dict[str, list[str]],
        key: str,
        default: int,
    ) -> int:
        value = self._query_value(params, key, str(default))
        return int(value)

    def _required_value(self, payload: Dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if value is None:
            raise ValueError("missing required field: " + key)
        text = str(value).strip()
        if not text:
            raise ValueError("missing required field: " + key)
        return text


def create_phone_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    store_path: Optional[str] = None,
) -> PhoneHTTPServer:
    """Create a configured local server for the Phone web app."""

    app = PhoneWebApplication(
        store_path=store_path,
    )
    return PhoneHTTPServer((host, port), PhoneRequestHandler, app)


def run_phone_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    store_path: Optional[str] = None,
) -> None:
    """Run the local Phone web app until interrupted."""

    server = create_phone_server(
        host=host,
        port=port,
        store_path=store_path,
    )
    address = server.server_address
    print(
        "Phone web app is running at http://{host}:{port}".format(
            host=address[0],
            port=address[1],
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    """CLI entry point for the standalone Phone web app."""

    parser = argparse.ArgumentParser(description="Run the standalone Phone web app.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", default=8765, type=int, help="Port to bind.")
    parser.add_argument(
        "--store",
        default=None,
        help="Optional JSON store path for chat persistence.",
    )
    args = parser.parse_args()

    run_phone_server(
        host=args.host,
        port=args.port,
        store_path=args.store,
    )


if __name__ == "__main__":
    main()
