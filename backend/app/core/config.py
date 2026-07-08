from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://lanparty:lanparty@database:5432/lanparty"
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
    analytics_retention_days: int = 180
    privacy_controller_name: str = "Betreiber:in dieser Installation"
    privacy_controller_contact: str = "Kontakt über den internen LAN-Party-Gruppenkanal"
    privacy_hosting_provider: str = "VServer-Hostinganbieter der Betreiberperson"
    privacy_access_log_retention_days: int = 7
    privacy_backup_retention_days: int = 14
    privacy_supervisory_authority: str = "Zuständige Landesdatenschutzaufsichtsbehörde"
    privacy_supervisory_authority_url: str = "https://www.datenschutzkonferenz-online.de/datenschutzaufsichtsbehoerden.html"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()






