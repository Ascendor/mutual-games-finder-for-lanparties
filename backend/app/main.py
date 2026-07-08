from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from threading import Thread

from app.api import accounts, analytics, games, imports, ownerships, participants, privacy, provider_auth, recommendations, sync
from app.api.imports import remove_stale_uploads
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.metadata_service import close_interrupted_metadata_runs
from app.services.playnite_import import close_interrupted_playnite_runs
from app.services.recommendation_cache import warm_dashboard_recommendations
from app.services.analytics_service import purge_expired_usage_events
from app.services.steam_metadata_service import close_interrupted_steam_metadata_runs

app = FastAPI(title="LAN Party Game Finder", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(participants.router, prefix="/api/participants", tags=["participants"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(games.router, prefix="/api/games", tags=["games"])
app.include_router(ownerships.router, prefix="/api/ownerships", tags=["ownerships"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(provider_auth.router, prefix="/api/provider-auth", tags=["provider-auth"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
app.include_router(imports.router, prefix="/api/imports", tags=["imports"])
app.include_router(analytics.router, prefix="/api/app-log", tags=["app-log"])
app.include_router(privacy.router, prefix="/api/privacy", tags=["privacy"])


@app.on_event("startup")
def close_interrupted_syncs_on_startup() -> None:
    remove_stale_uploads()
    db = SessionLocal()
    try:
        purge_expired_usage_events(db)
        close_interrupted_metadata_runs(db)
        close_interrupted_playnite_runs(db)
        close_interrupted_steam_metadata_runs(db)
    finally:
        db.close()
    Thread(
        target=warm_dashboard_recommendations,
        name="recommendation-cache-warmup",
        daemon=True,
    ).start()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
