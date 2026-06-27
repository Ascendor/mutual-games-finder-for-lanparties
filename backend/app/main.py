from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, games, imports, ownerships, participants, provider_auth, recommendations, sync
from app.core.config import settings

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



@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

