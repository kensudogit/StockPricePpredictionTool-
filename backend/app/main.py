from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.analysis_routes import router as analysis_router
from app.api.routes import router
from app.api.tests_routes import RESULTS_DIR, router as tests_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


FALLBACK_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>StockAI</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#0c1210; color:#e8f0eb; margin:0; padding:2rem; }
    a { color:#3dd68c; }
    .card { max-width:640px; margin:4rem auto; padding:2rem; border:1px solid #2a3a32; border-radius:12px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>StockAI</h1>
    <p>API は稼働しています。フロント静的ファイルが見つかりませんでした。</p>
    <p><a href="/docs">API Docs</a> · <a href="/api/v1/health">Health</a></p>
  </div>
</body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="StockAI Agent Platform",
        description="株価予測・売買判断・リスク管理・SNS運用を統合するAIエージェントAPI",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    app.include_router(tests_router, prefix="/api/v1")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/test-results", StaticFiles(directory=RESULTS_DIR, html=True), name="test_results")

    index_file = STATIC_DIR / "index.html"
    next_dir = STATIC_DIR / "_next"

    if next_dir.is_dir():
        app.mount("/_next", StaticFiles(directory=next_dir), name="next_assets")

    @app.get("/", include_in_schema=False)
    async def serve_root():
        if index_file.is_file():
            return FileResponse(index_file)
        return HTMLResponse(FALLBACK_HTML)

    if STATIC_DIR.is_dir():

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            # Never shadow API / OpenAPI UI
            blocked_prefixes = ("api/", "docs", "redoc", "openapi.json", "test-results")
            if full_path.startswith(blocked_prefixes) or full_path in {"docs", "redoc", "openapi.json"}:
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            nested = STATIC_DIR / full_path / "index.html"
            if nested.is_file():
                return FileResponse(nested)
            if index_file.is_file():
                return FileResponse(index_file)
            return HTMLResponse(FALLBACK_HTML, status_code=404)

    return app


app = create_app()
