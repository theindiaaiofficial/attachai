
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from app.main import app as orbit_application

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


async def dispatch(request: Request):
    original_method = request.method
    method = "GET" if original_method == "HEAD" else original_method

    body = await request.body()
    client_ip = request.client.host if request.client else "127.0.0.1"

    result = await run_in_threadpool(
        orbit_application.handle_http,
        method=method,
        url_or_path=str(request.url),
        headers=dict(request.headers),
        body=body,
        cookies=dict(request.cookies),
        client_ip=client_ip,
    )

    status_code = int(result.get("status_code", 500))
    headers = result.get("headers") or {}
    response_body = result.get("body", "")

    if original_method == "HEAD":
        response = Response(
            content=b"",
            status_code=status_code,
            headers=headers,
        )
    elif isinstance(response_body, (dict, list)):
        response = JSONResponse(
            content=response_body,
            status_code=status_code,
            headers=headers,
        )
    else:
        response = Response(
            content=response_body or "",
            status_code=status_code,
            headers=headers,
        )

    for name, value in (result.get("cookies") or {}).items():
        response.set_cookie(
            key=name,
            value=value,
            httponly=True,
            secure=orbit_application.container.settings.is_production,
            samesite="lax",
            path="/",
        )

    return response


methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

app.add_api_route("/", dispatch, methods=methods)
app.add_api_route("/{path:path}", dispatch, methods=methods)
