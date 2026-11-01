"""Main application entrypoint for Orbit AI (compatible with both FastAPI/Uvicorn and stdlib TestClient)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from app.api.admin import AdminApiController
from app.api.public import PublicApiController
from app.api.system import SystemApiController
from app.core.dependencies import ServiceContainer
from app.core.exceptions import NotFoundError, OrbitError
from app.middleware.cors import build_security_and_cors_headers
from app.middleware.request_context import get_or_create_request_id


@dataclass
class HttpResponseEnvelope:
    status_code: int
    headers: Dict[str, str]
    body: Any
    cookies: Dict[str, str]

    def json(self) -> Any:
        if isinstance(self.body, (dict, list)):
            return self.body
        if isinstance(self.body, bytes):
            return json.loads(self.body.decode("utf-8"))
        return json.loads(str(self.body))

    @property
    def text(self) -> str:
        if isinstance(self.body, str):
            return self.body
        if isinstance(self.body, bytes):
            return self.body.decode("utf-8", errors="replace")
        return json.dumps(self.body)


class OrbitApplication:
    """
    Unified Orbit AI ASGI & HTTP application.
    Serves all public `/v1/*`, admin `/admin/*`, system `/health`, `/ready`, `/metrics`,
    and static `/static/*` & `/demo.html` routes.
    """

    def __init__(self, container: Optional[ServiceContainer] = None) -> None:
        self.container = container or ServiceContainer()
        self.public_api = PublicApiController(self.container)
        self.admin_api = AdminApiController(self.container)
        self.system_api = SystemApiController(self.container)
        self._root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def _read_project_file(self, rel_path: str) -> Tuple[bytes, str]:
        safe_rel = rel_path.lstrip("/\\")
        full = os.path.abspath(os.path.join(self._root_dir, safe_rel))
        if not full.startswith(self._root_dir) or not os.path.isfile(full):
            raise NotFoundError(f"Asset not found: {rel_path}")
        ext = os.path.splitext(full)[1].lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            return f.read(), content_type

    def handle_http(
        self,
        method: str,
        url_or_path: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
        cookies: Optional[Dict[str, str]] = None,
        client_ip: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        req_headers = {k: v for k, v in (headers or {}).items()}
        req_cookies = dict(cookies or {})
        parsed = urlparse(url_or_path)
        path = parsed.path or "/"
        query_params = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}

        request_id = get_or_create_request_id(req_headers)
        origin = req_headers.get("Origin") or req_headers.get("origin") or ""
        resp_headers = build_security_and_cors_headers(
            origin=origin,
            allowed_origins=self.container.settings.effective_cors_origins,
            is_production=self.container.settings.is_production,
        )
        resp_headers["X-Request-Id"] = request_id
        resp_cookies: Dict[str, str] = {}

        if method.upper() == "OPTIONS":
            return {
                "status_code": 204,
                "headers": resp_headers,
                "body": "",
                "cookies": resp_cookies,
            }

        payload: Dict[str, Any] = {}
        if isinstance(body, dict):
            payload = body
        elif isinstance(body, (str, bytes)) and body:
            try:
                raw_str = body.decode("utf-8") if isinstance(body, bytes) else body
                payload = json.loads(raw_str)
            except Exception:
                payload = {}

        try:
            m = method.upper()

            # 1. System endpoints
            if m == "GET" and path == "/health":
                code, data = self.system_api.get_health()
                return {"status_code": code, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "GET" and path == "/ready":
                code, data = self.system_api.get_ready()
                return {"status_code": code, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "GET" and path == "/metrics":
                data = self.system_api.get_metrics(req_headers, req_cookies)
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            # 2. Static & HTML routes
            if m == "GET" and path in ("/", "/admin"):
                raw, ctype = self._read_project_file("app/templates/dashboard.html")
                resp_headers["Content-Type"] = ctype
                return {"status_code": 200, "headers": resp_headers, "body": raw.decode("utf-8"), "cookies": resp_cookies}

            if m == "GET" and path == "/admin/login":
                raw, ctype = self._read_project_file("app/templates/login.html")
                resp_headers["Content-Type"] = ctype
                return {"status_code": 200, "headers": resp_headers, "body": raw.decode("utf-8"), "cookies": resp_cookies}

            if m == "GET" and path == "/demo.html":
                raw, ctype = self._read_project_file("public/demo.html")
                resp_headers["Content-Type"] = ctype
                return {"status_code": 200, "headers": resp_headers, "body": raw.decode("utf-8"), "cookies": resp_cookies}

            if m == "GET" and path.startswith("/static/"):
                raw, ctype = self._read_project_file(path.lstrip("/"))
                resp_headers["Content-Type"] = ctype
                return {"status_code": 200, "headers": resp_headers, "body": raw.decode("utf-8"), "cookies": resp_cookies}

            # 3. Public v1 Widget APIs
            if m == "GET" and path == "/v1/config":
                data = self.public_api.get_config(
                    req_headers,
                    client_ip=client_ip,
                    expected_client_id=query_params.get("clientId"),
                )
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "POST" and path == "/v1/chat":
                data = self.public_api.post_chat(req_headers, payload, client_ip=client_ip)
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "POST" and path == "/v1/chat/stream":
                sse_gen = self.public_api.post_chat_stream(req_headers, payload, client_ip=client_ip)
                sse_text = "".join(list(sse_gen))
                resp_headers["Content-Type"] = "text/event-stream; charset=utf-8"
                resp_headers["Cache-Control"] = "no-cache"
                resp_headers["Connection"] = "keep-alive"
                return {"status_code": 200, "headers": resp_headers, "body": sse_text, "cookies": resp_cookies}

            if m == "POST" and path == "/v1/feedback":
                data = self.public_api.post_feedback(req_headers, payload, client_ip=client_ip)
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "POST" and path == "/v1/leads":
                data = self.public_api.post_leads(req_headers, payload, client_ip=client_ip)
                return {"status_code": 201 if data.get("created") else 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            # 4. Admin APIs
            if m == "POST" and path == "/admin/api/login":
                session_token, csrf_token = self.admin_api.login(str(payload.get("apiKey") or ""))
                resp_cookies["orbit_admin_session"] = session_token
                return {
                    "status_code": 200,
                    "headers": resp_headers,
                    "body": {"authenticated": True, "csrfToken": csrf_token},
                    "cookies": resp_cookies,
                }

            if m == "GET" and path == "/admin/api/overview":
                data = self.admin_api.get_overview(req_headers, req_cookies)
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "GET" and path == "/admin/api/tenants":
                data = self.admin_api.list_tenants(req_headers, req_cookies)
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "POST" and path == "/admin/api/tenants":
                data = self.admin_api.create_tenant(req_headers, payload, req_cookies)
                return {"status_code": 201, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if path.startswith("/admin/api/tenants/"):
                parts = [p for p in path.split("/") if p]
                # parts: ['admin', 'api', 'tenants', '<client_id>', ...]
                client_id = parts[3]
                if len(parts) == 4:
                    if m == "GET":
                        data = self.admin_api.get_tenant_detail(req_headers, client_id, req_cookies)
                        return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                    if m in ("PATCH", "PUT"):
                        data = self.admin_api.update_tenant(req_headers, client_id, payload, req_cookies)
                        return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                    if m == "DELETE":
                        data = self.admin_api.delete_tenant(req_headers, client_id, req_cookies)
                        return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                elif len(parts) == 5 and parts[4] == "duplicate" and m == "POST":
                    data = self.admin_api.duplicate_tenant(req_headers, client_id, payload, req_cookies)
                    return {"status_code": 201, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                elif len(parts) == 5 and parts[4] == "rotate-key" and m == "POST":
                    data = self.admin_api.rotate_key(
                        req_headers,
                        client_id,
                        label=str(payload.get("label") or "Rotated Widget Key"),
                        cookies=req_cookies,
                    )
                    return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                elif len(parts) == 5 and parts[4] == "domains":
                    if m == "POST":
                        domains = self.container.client_service.add_domain(client_id, str(payload.get("domain") or ""))
                        return {"status_code": 200, "headers": resp_headers, "body": {"domains": domains}, "cookies": resp_cookies}
                    if m == "DELETE":
                        domains = self.container.client_service.remove_domain(client_id, str(payload.get("domain") or query_params.get("domain") or ""))
                        return {"status_code": 200, "headers": resp_headers, "body": {"domains": domains}, "cookies": resp_cookies}
                elif len(parts) == 5 and parts[4] == "prompts" and m == "POST":
                    self.admin_api.authorize(req_headers, req_cookies, "POST")
                    version = self.container.client_service.save_prompt_version(
                        client_id=client_id,
                        system_prompt=str(payload.get("systemPrompt") or payload.get("system_prompt") or ""),
                        fallback_answer=payload.get("fallbackAnswer") or payload.get("fallback_answer"),
                        welcome_message=payload.get("welcomeMessage") or payload.get("welcome_message"),
                        note=str(payload.get("note") or ""),
                    )
                    return {"status_code": 201, "headers": resp_headers, "body": {"promptVersion": asdict(version)}, "cookies": resp_cookies}
                elif len(parts) == 6 and parts[4] == "prompts" and parts[5] == "restore" and m == "POST":
                    self.admin_api.authorize(req_headers, req_cookies, "POST")
                    updated = self.container.client_service.restore_prompt_version(
                        client_id=client_id,
                        version_number=int(payload.get("versionNumber") or payload.get("version_number") or 1),
                    )
                    return {"status_code": 200, "headers": resp_headers, "body": {"tenant": asdict(updated)}, "cookies": resp_cookies}
                elif len(parts) == 5 and parts[4] == "knowledge" and m == "POST":
                    raw_content = payload.get("content")
                    if isinstance(raw_content, str):
                        file_bytes = raw_content.encode("utf-8")
                    elif isinstance(raw_content, bytes):
                        file_bytes = raw_content
                    else:
                        file_bytes = b""
                    data = self.admin_api.upload_knowledge(
                        headers=req_headers,
                        client_id=client_id,
                        filename=str(payload.get("filename") or "document.txt"),
                        content=file_bytes,
                        mime_type=str(payload.get("mimeType") or "text/plain"),
                        cookies=req_cookies,
                    )
                    return {"status_code": 201, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                elif len(parts) == 6 and parts[4] == "knowledge" and m == "DELETE":
                    file_id = parts[5]
                    data = self.admin_api.delete_knowledge(req_headers, client_id, file_id, req_cookies)
                    return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}
                elif len(parts) == 7 and parts[4] == "knowledge" and parts[6] == "rebuild" and m == "POST":
                    file_id = parts[5]
                    data = self.admin_api.rebuild_knowledge(req_headers, client_id, file_id, req_cookies)
                    return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "GET" and path == "/admin/api/conversations":
                data = self.admin_api.list_conversations(
                    req_headers,
                    client_id=query_params.get("clientId"),
                    search=query_params.get("search", ""),
                    cookies=req_cookies,
                )
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "GET" and path.startswith("/admin/api/conversations/"):
                conv_id = path.rstrip("/").split("/")[-1]
                client_id = query_params.get("clientId") or ""
                data = self.admin_api.get_conversation_messages(req_headers, client_id, conv_id, req_cookies)
                return {"status_code": 200, "headers": resp_headers, "body": data, "cookies": resp_cookies}

            if m == "GET" and path == "/admin/api/leads":
                self.admin_api.authorize(req_headers, req_cookies, "GET")
                leads = self.container.lead_service.list_leads(
                    client_id=query_params.get("clientId"),
                    status=query_params.get("status"),
                    search=query_params.get("search", ""),
                )
                return {"status_code": 200, "headers": resp_headers, "body": {"leads": [asdict(l) for l in leads]}, "cookies": resp_cookies}

            if m == "GET" and path == "/admin/api/leads/export":
                self.admin_api.authorize(req_headers, req_cookies, "GET")
                csv_text = self.container.lead_service.export_csv(
                    client_id=query_params.get("clientId"),
                    status=query_params.get("status"),
                )
                resp_headers["Content-Type"] = "text/csv; charset=utf-8"
                return {"status_code": 200, "headers": resp_headers, "body": csv_text, "cookies": resp_cookies}

            if m in ("PATCH", "PUT") and path.startswith("/admin/api/leads/"):
                self.admin_api.authorize(req_headers, req_cookies, m)
                lead_id = path.rstrip("/").split("/")[-1]
                client_id = str(payload.get("clientId") or payload.get("client_id") or query_params.get("clientId") or "")
                updated = self.container.lead_service.update_lead(
                    client_id=client_id,
                    lead_id=lead_id,
                    status=payload.get("status"),
                    assignee=payload.get("assignee"),
                    notes=payload.get("notes"),
                )
                return {"status_code": 200, "headers": resp_headers, "body": {"lead": asdict(updated)}, "cookies": resp_cookies}

            if m == "GET" and path == "/admin/api/analytics":
                self.admin_api.authorize(req_headers, req_cookies, "GET")
                summary = self.container.analytics_service.get_summary(
                    client_id=query_params.get("clientId"),
                    start_date=query_params.get("startDate"),
                    end_date=query_params.get("endDate"),
                )
                return {"status_code": 200, "headers": resp_headers, "body": summary, "cookies": resp_cookies}

            raise NotFoundError(f"Route not found: {m} {path}")

        except OrbitError as err:
            self.container.logger.warning(
                "http.orbit_error",
                code=err.code,
                statusCode=err.status_code,
                message=err.message,
                path=path,
            )
            return {
                "status_code": err.status_code,
                "headers": resp_headers,
                "body": {"error": {"code": err.code, "message": err.message, "details": err.details}},
                "cookies": resp_cookies,
            }
        except Exception as exc:
            self.container.logger.error("http.unhandled_exception", path=path, error=str(exc))
            return {
                "status_code": 500,
                "headers": resp_headers,
                "body": {"error": {"code": "internal_error", "message": "An unexpected internal error occurred."}},
                "cookies": resp_cookies,
            }


class OrbitTestClient:
    """Synchronous HTTP test client for OrbitApplication."""

    def __init__(self, app: OrbitApplication, client_ip: str = "127.0.0.1") -> None:
        self.app = app
        self.client_ip = client_ip
        self.cookies: Dict[str, str] = {}

    def request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Any] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> HttpResponseEnvelope:
        merged_cookies = {**self.cookies, **(cookies or {})}
        raw = self.app.handle_http(
            method=method,
            url_or_path=path,
            headers=headers,
            body=json_body,
            cookies=merged_cookies,
            client_ip=self.client_ip,
        )
        for k, v in raw.get("cookies", {}).items():
            self.cookies[k] = v
        return HttpResponseEnvelope(
            status_code=raw["status_code"],
            headers=raw["headers"],
            body=raw["body"],
            cookies=raw.get("cookies", {}),
        )

    def get(self, path: str, headers: Optional[Dict[str, str]] = None, cookies: Optional[Dict[str, str]] = None) -> HttpResponseEnvelope:
        return self.request("GET", path, headers=headers, cookies=cookies)

    def post(
        self,
        path: str,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> HttpResponseEnvelope:
        return self.request("POST", path, headers=headers, json_body=json, cookies=cookies)

    def patch(
        self,
        path: str,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> HttpResponseEnvelope:
        return self.request("PATCH", path, headers=headers, json_body=json, cookies=cookies)

    def delete(
        self,
        path: str,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> HttpResponseEnvelope:
        return self.request("DELETE", path, headers=headers, json_body=json, cookies=cookies)


def create_app(container: Optional[ServiceContainer] = None) -> OrbitApplication:
    return OrbitApplication(container=container)


app = create_app()
