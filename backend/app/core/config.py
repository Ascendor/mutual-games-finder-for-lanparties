from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://lanparty:lanparty@database:5432/lanparty"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    admin_password: str | None = None
    steam_api_key: str | None = None
    steam_metadata_limit: int = 2000
    steam_store_timeout_seconds: float = 8.0
    steam_metadata_workers: int = 4
    steam_metadata_budget_seconds: float = 90.0
    steam_helper_url: str = "http://steam-helper:3000"
    steam_helper_timeout_seconds: float = 15.0
    rawg_api_key: str | None = None
    igdb_client_id: str | None = None
    igdb_client_secret: str | None = None
    legendary_command: str = "legendary"
    provider_auth_root: str = "/provider-auth"
    gog_auth_config_path: str | None = None
    xbox_client_id: str | None = None
    gog_client_id: str = "46899977096215655"
    gog_client_secret: str = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
    gog_auth_url: str = "https://auth.gog.com/token"
    gog_login_url: str = "https://auth.gog.com/auth"
    gog_redirect_uri: str = "https://embed.gog.com/on_login_success?origin=client"
    gog_embed_url: str = "https://embed.gog.com"
    gog_api_url: str = "https://api.gog.com"
    epic_login_url: str = "https://legendary.gl/epiclogin"
    ubisoft_app_id: str = "f68a4bb5-608a-4ff2-8123-be8ef797e0a6"
    ubisoft_club_graphql_url: str = "https://public-ubiservices.ubi.com/v1/profiles/me/uplay/graphql"
    amazon_device_type: str = "A2UMVHOX7UP4V7"
    amazon_login_url: str = "https://www.amazon.com/ap/signin"
    amazon_entitlements_url: str = "https://gaming.amazon.com/api/distribution/entitlements"
    amazon_token_url: str = "https://api.amazon.com/auth/token"
    ea_graphql_url: str = "https://service-aggregation-layer.juno.ea.com/graphql"
    ea_owned_games_query_hash: str = "779f1cd1355699752e20c0b3877847f4e3010ef5de131c248e98f8eff84f0718"
    ea_play_times_query_hash: str = "3f09b35e06b75c74d8ec3e520a598ebb5e2992b1e1268b6dd3b8ed99b9fafb29"
    ea_identity_url: str = "https://gateway.ea.com/proxy/identity/pids/me"
    ea_origin_api_base_urls: str = "https://api1.origin.com,https://api2.origin.com,https://api3.origin.com,https://api4.origin.com"
    meta_graphql_url: str = "https://graph.oculus.com/graphql?locale=en_US"
    meta_graphql_document_ids: str = "9431935310238631,29383114651302983,29143116735333849"
    playnite_upload_dir: str = "/tmp/playnite-uploads"
    playnite_upload_max_bytes: int = 4 * 1024 * 1024 * 1024
    games_options_cache_seconds: int = 300
    games_options_stale_seconds: int = 60
    recommendation_http_cache_seconds: int = 30
    recommendation_cache_entry_ttl_seconds: int = 3600
    recommendation_cache_max_entries: int = 64
    recommendation_common_minimum_coverage_default: int = 75
    recommendation_optional_unsynced_platforms: str = "ea"
    recommendation_playtime_cap_minutes: int = 20000
    recommendation_median_playtime_cap_minutes: int = 5000
    recommendation_playtime_divisor: float = 100.0
    recommendation_median_playtime_divisor: float = 100.0
    recommendation_capacity_fit_bonus: float = 300.0
    recommendation_common_adoption_weight: float = 1000.0
    recommendation_common_median_weight: float = 2.0
    recommendation_common_multiplayer_bonus: float = 150.0
    recommendation_coop_adoption_weight: float = 1000.0
    recommendation_coop_online_bonus: float = 500.0
    recommendation_coop_local_bonus: float = 250.0
    recommendation_coop_screen_bonus: float = 100.0
    recommendation_lan_owner_weight: float = 1200.0
    recommendation_lan_bonus: float = 300.0
    recommendation_group_owner_weight: float = 1000.0
    recommendation_group_multiplayer_bonus: float = 150.0
    recommendation_new_owner_weight: float = 1500.0
    recommendation_new_freshness_base_minutes: float = 5000.0
    recommendation_new_freshness_divisor: float = 10.0
    recommendation_new_playtime_penalty_divisor: float = 200.0
    recommendation_popular_adoption_weight: float = 5000.0
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




