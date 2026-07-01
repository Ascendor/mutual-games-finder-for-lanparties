from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://lanparty:lanparty@database:5432/lanparty"
    sqlite_migration_path: str | None = "/legacy-data/lan_party_game_finder_migration_snapshot.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    steam_api_key: str | None = None
    steam_metadata_limit: int = 2000
    steam_store_timeout_seconds: float = 8.0
    steam_metadata_workers: int = 4
    steam_metadata_budget_seconds: float = 90.0
    rawg_api_key: str | None = None
    igdb_client_id: str | None = None
    igdb_client_secret: str | None = None
    legendary_command: str = "legendary"
    provider_auth_root: str = "/provider-auth"
    gog_auth_config_path: str | None = None
    xbox_client_id: str | None = None
    playnite_upload_dir: str = "/tmp/playnite-uploads"
    playnite_upload_max_bytes: int = 4 * 1024 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()






