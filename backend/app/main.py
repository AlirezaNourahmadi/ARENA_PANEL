import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from .config import get_settings
from .database import SessionLocal
from .migrations import migrate_database
from .models import Admin, Node
from .routes import auth, dashboard, gateway, nodes, subscriptions, users
from .security import hash_password
from .services.audit import audit
from .xray import xray_runtime


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("arena")
settings = get_settings()


def seed_database() -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.username == settings.admin_username))
        if not admin:
            admin = Admin(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
            )
            db.add(admin)
            db.flush()
            audit(db, "admin.seeded", entity_type="admin", entity_id=admin.id)

        secure = settings.public_url.startswith("https://")
        defaults = [
            ("ARENA VLESS", "arena-vless", "vless"),
            ("ARENA VMess", "arena-vmess", "vmess"),
        ]
        for name, slug, protocol in defaults:
            if not db.scalar(select(Node).where(Node.slug == slug)):
                db.add(
                    Node(
                        name=name,
                        slug=slug,
                        kind="xray",
                        protocol=protocol,
                        transport="websocket",
                        host=settings.xray_public_host,
                        port=settings.xray_public_port,
                        security="tls" if secure else "none",
                        sni=settings.xray_public_host if secure else "",
                        websocket_host=settings.xray_public_host,
                        path=settings.gateway_public_path,
                        fingerprint="chrome",
                        alpn="http/1.1",
                    )
                )
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_database()
    seed_database()
    with SessionLocal() as db:
        await xray_runtime.start(db)
    yield
    await xray_runtime.stop()


app = FastAPI(
    title="ARENA Control Plane",
    version="0.1.0",
    docs_url="/api/docs" if settings.env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_url] if settings.env == "development" else [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Arena-Gateway"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(nodes.router)
app.include_router(gateway.router)
app.include_router(dashboard.router)
app.include_router(subscriptions.router)


@app.get("/api/health")
def health() -> JSONResponse:
    database_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database_ok = True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
    xray_ok = xray_runtime.running if settings.xray_enabled else True
    healthy = database_ok and xray_ok
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "database": "ok" if database_ok else "failed",
            "xray": "running" if xray_runtime.running else ("disabled" if not settings.xray_enabled else "stopped"),
            "version": app.version,
        },
        status_code=200 if healthy else 503,
    )


frontend_dist = Path("/app/frontend/dist")
if not frontend_dist.exists():
    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if frontend_dist.exists():
    assets = frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/") or path.startswith("sub/"):
            raise HTTPException(status_code=404)
        target = frontend_dist / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(frontend_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_frontend():
        return {"name": "ARENA", "message": "Frontend build is not present"}
