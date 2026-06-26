from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, games, ownerships, participants, provider_auth, recommendations, sync
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.metadata_repair import repair_legacy_steam_metadata

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



@app.on_event("startup")
def repair_metadata_on_startup() -> None:
    db = SessionLocal()
    try:
        repair_legacy_steam_metadata(db)
    finally:
        db.close()
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

