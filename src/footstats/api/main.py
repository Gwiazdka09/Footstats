"""FootStats API — app factory with auth, CORS, rate limiting, and timeout."""
import asyncio
import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")

load_dotenv()

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn and _sentry_dsn.startswith("https://"):
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.1,
        environment=os.environ.get("ENV", "production"),
    )


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record),
            "request_id": _request_id_var.get(""),
        })


class _RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        _request_id_var.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class _TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout: float = 10.0) -> None:
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                {"detail": "Request timeout", "timeout_s": self.timeout},
                status_code=504,
            )


class _MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from footstats.core.logging_config import metrics
        t0 = time.perf_counter()
        response = await call_next(request)
        dt = time.perf_counter() - t0
        metrics.record_request(request.url.path, response.status_code, dt)
        return response


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)

from footstats.api.auth import router as auth_router
from footstats.api.routes.bankroll import router as bankroll_router
from footstats.api.routes.coupons import router as coupons_router
from footstats.api.routes.settings import router as settings_router
from footstats.api.routes.status import router as status_router

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

def _init_db() -> None:
    from footstats.utils.db import connect
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS coupons (
                id               SERIAL PRIMARY KEY,
                created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                phase            TEXT NOT NULL DEFAULT '',
                status           TEXT NOT NULL DEFAULT 'DRAFT',
                kupon_type       TEXT NOT NULL DEFAULT '',
                legs_json        TEXT NOT NULL DEFAULT '[]',
                total_odds       REAL,
                stake_pln        REAL,
                payout_pln       REAL,
                roi_pct          REAL,
                groq_reasoning   TEXT,
                decision_score   INTEGER,
                match_date_first TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_coupon_status  ON coupons(status);
            CREATE INDEX IF NOT EXISTS idx_coupon_created ON coupons(created_at);

            CREATE TABLE IF NOT EXISTS predictions (
                id                   SERIAL PRIMARY KEY,
                created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                match_date           TEXT NOT NULL,
                team_home            TEXT NOT NULL,
                team_away            TEXT NOT NULL,
                league               TEXT NOT NULL DEFAULT '',
                ai_tip               TEXT NOT NULL DEFAULT '',
                ai_confidence        INTEGER NOT NULL DEFAULT 0 CHECK(ai_confidence BETWEEN 0 AND 100),
                ai_reasoning         TEXT NOT NULL DEFAULT '',
                odds                 REAL,
                actual_result        TEXT,
                tip_correct          INTEGER CHECK(tip_correct IN (0, 1)),
                kupon_type           TEXT DEFAULT '',
                kodeks_rules_checked TEXT NOT NULL DEFAULT '[]',
                prompt_version       TEXT NOT NULL DEFAULT '',
                factors              TEXT NOT NULL DEFAULT '[]',
                match_stats          TEXT,
                coupon_id            INTEGER REFERENCES coupons(id)
            );
            CREATE INDEX IF NOT EXISTS idx_match_date  ON predictions(match_date);
            CREATE INDEX IF NOT EXISTS idx_tip_correct ON predictions(tip_correct);
            CREATE INDEX IF NOT EXISTS idx_kupon_type  ON predictions(kupon_type);
            CREATE INDEX IF NOT EXISTS idx_league      ON predictions(league);

            CREATE TABLE IF NOT EXISTS ai_feedback (
                id                  SERIAL PRIMARY KEY,
                match_id            INTEGER NOT NULL REFERENCES predictions(id),
                prediction_details  TEXT NOT NULL DEFAULT '{}',
                reason_for_failure  TEXT NOT NULL DEFAULT '',
                created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_ai_feedback_match ON ai_feedback(match_id);
            CREATE INDEX IF NOT EXISTS idx_ai_feedback_date  ON ai_feedback(created_at);

            CREATE TABLE IF NOT EXISTS ai_feedback_embeddings (
                feedback_id INTEGER PRIMARY KEY REFERENCES ai_feedback(id) ON DELETE CASCADE,
                embedding   BYTEA NOT NULL,
                model_name  TEXT NOT NULL,
                dim         INTEGER NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bankroll_state (
                id         INTEGER PRIMARY KEY CHECK (id = 1),
                balance    REAL NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bankroll_history (
                id          SERIAL PRIMARY KEY,
                timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                change_pln  REAL NOT NULL,
                new_balance REAL NOT NULL,
                type        TEXT NOT NULL,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS bot_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wf_results (
                id         SERIAL PRIMARY KEY,
                run_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                league     TEXT NOT NULL,
                match_date TEXT NOT NULL,
                home       TEXT NOT NULL,
                away       TEXT NOT NULL,
                actual_hg  INTEGER,
                actual_ag  INTEGER,
                actual_res TEXT,
                pred_res   TEXT,
                pred_conf  REAL,
                pred_tip   TEXT,
                lambda_h   REAL,
                lambda_a   REAL,
                form_h     REAL,
                form_a     REAL,
                elo_diff   REAL,
                correct    INTEGER,
                market     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_wf_league  ON wf_results(league);
            CREATE INDEX IF NOT EXISTS idx_wf_correct ON wf_results(correct)
        """)

import logging as _logging
try:
    _init_db()
    from footstats.db.migrations import run_migrations, seed_admin_user
    run_migrations()
    seed_admin_user()
except Exception as _db_err:
    _logging.getLogger(__name__).error("DB init failed: %s", _db_err, exc_info=True)

app = FastAPI(title="FootStats API", version="2.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(_MetricsMiddleware)
app.add_middleware(_TimeoutMiddleware, timeout=10.0)
app.add_middleware(_RequestIDMiddleware)

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(status_router)
app.include_router(bankroll_router)
app.include_router(settings_router)
app.include_router(coupons_router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    from footstats import __version__

    auth_ok: bool = False
    auth_detail: str = "unknown"
    try:
        from footstats.utils.db import connect
        with connect() as _conn:
            row = _conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE is_active = TRUE"
            ).fetchone()
            n = (row["n"] if row else 0) if hasattr(row, "keys") else (row[0] if row else 0)
        auth_ok = n > 0
        auth_detail = f"{n} aktywny/ch uzytkownik/ow"
    except (OSError, ValueError, RuntimeError) as _e:
        auth_detail = f"db-error: {_e}"

    return {
        "status": "ok",
        "version": __version__,
        "auth": {"ok": auth_ok, "detail": auth_detail},
    }


@app.get("/metrics", tags=["ops"])
def metrics_endpoint():
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from starlette.responses import Response
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        return {"status": "metrics-disabled", "reason": "prometheus_client not installed"}


from fastapi_mcp import FastApiMCP as _FastApiMCP

_mcp = _FastApiMCP(app)
_mcp.mount_http()

_dist = Path(__file__).parent.parent / "gui" / "dist"

if _dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/")
    def root():
        return FileResponse(str(_dist / "index.html"), media_type="text/html")

    @app.get("/app")
    def serve_app():
        return FileResponse(str(_dist / "index.html"), media_type="text/html")
else:
    @app.get("/")
    def root():
        return RedirectResponse(url="/preview")

    @app.get("/preview")
    def serve_preview():
        html_path = Path(__file__).parent / "preview.html"
        return FileResponse(html_path, media_type="text/html",
                            headers={"Cache-Control": "no-store"})


@app.get("/manifest.json", tags=["pwa"])
def pwa_manifest():
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "name": "FootStats",
        "short_name": "FootStats",
        "description": "Kreator kuponów piłkarskich",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#6366f1",
        "lang": "pl",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.get("/sw.js", tags=["pwa"])
def service_worker():
    from fastapi.responses import Response
    js = """
const CACHE = 'footstats-v1';
const PRECACHE = ['/preview'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
""".strip()
    return Response(js, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
