from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Platform


class ParticipantBase(BaseModel):
    nickname: str
    real_name: str | None = None
    present: bool = True
    notes: str = ""


class ParticipantCreate(ParticipantBase):
    pass


class ParticipantUpdate(BaseModel):
    nickname: str | None = None
    real_name: str | None = None
    present: bool | None = None
    notes: str | None = None


class ParticipantRead(ParticipantBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class AccountBase(BaseModel):
    participant_id: int
    platform: Platform
    account_id: str = ""
    display_name: str = ""


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    participant_id: int | None = None
    platform: Platform | None = None
    account_id: str | None = None
    display_name: str | None = None


class AccountRead(AccountBase):
    id: int
    last_successful_sync: datetime | None = None
    last_error: str | None = None
    model_config = ConfigDict(from_attributes=True)


class SteamProfileRead(BaseModel):
    steam_id: str
    display_name: str
    profile_url: str
    avatar_url: str | None = None
    library_accessible: bool
    game_count: int | None = None


class SteamConnectionRead(SteamProfileRead):
    account: AccountRead


class GameBase(BaseModel):
    title: str
    description: str = ""
    cover_url: str | None = None
    release_date: date | None = None
    genres: list[str] = Field(default_factory=list)
    is_game: bool = True
    non_game_reason: str | None = None
    is_free: bool = False
    singleplayer: bool = False
    multiplayer: bool = False
    lan: bool = False
    local_coop: bool = False
    online_coop: bool = False
    hotseat: bool = False
    split_screen: bool = False
    shared_screen: bool = False
    campaign_coop: bool = False
    drop_in: bool = False
    versus: bool = False
    min_players: int = 1
    max_players: int = 1
    offline_max_players: int | None = None
    online_max_players: int | None = None
    offline_coop_max_players: int | None = None
    online_coop_max_players: int | None = None
    multiplayer_metadata_known: bool = False
    player_count_known: bool = False
    metadata_source: str | None = None
    metadata_external_id: str | None = None
    metadata_sources: dict[str, str] = Field(default_factory=dict)
    metadata_updated_at: datetime | None = None


class GameCreate(GameBase):
    pass


class GameUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    cover_url: str | None = None
    release_date: date | None = None
    genres: list[str] | None = None
    is_game: bool | None = None
    non_game_reason: str | None = None
    is_free: bool | None = None
    singleplayer: bool | None = None
    multiplayer: bool | None = None
    lan: bool | None = None
    local_coop: bool | None = None
    online_coop: bool | None = None
    hotseat: bool | None = None
    split_screen: bool | None = None
    shared_screen: bool | None = None
    campaign_coop: bool | None = None
    drop_in: bool | None = None
    versus: bool | None = None
    min_players: int | None = None
    max_players: int | None = None
    offline_max_players: int | None = None
    online_max_players: int | None = None
    offline_coop_max_players: int | None = None
    online_coop_max_players: int | None = None
    multiplayer_metadata_known: bool | None = None
    player_count_known: bool | None = None


class GameRead(GameBase):
    id: int
    normalized_title: str
    model_config = ConfigDict(from_attributes=True)


class GameListItemRead(GameRead):
    owner_count: int = 0


class GamePageRead(BaseModel):
    items: list[GameListItemRead]
    total: int
    page: int
    per_page: int
    genres: list[str] = Field(default_factory=list)


class GameOptionRead(BaseModel):
    id: int
    title: str
    model_config = ConfigDict(from_attributes=True)


class OwnershipCreate(BaseModel):
    participant_id: int
    account_id: int | None = None
    game_id: int
    platform: Platform
    playtime_minutes: int = 0
    owned_since: datetime | None = None


class OwnershipRead(OwnershipCreate):
    id: int
    owned_since_source: str | None = None
    first_seen_at: datetime | None = None
    first_seen_is_baseline: bool = False
    last_seen: datetime
    model_config = ConfigDict(from_attributes=True)


class PersonalGamePlatformRead(BaseModel):
    platform: Platform
    playtime_minutes: int = 0
    account_id: str | None = None
    account_display_name: str | None = None


class PersonalGameRead(BaseModel):
    game: GameRead
    platforms: list[PersonalGamePlatformRead] = Field(default_factory=list)
    total_playtime_minutes: int = 0


class PersonalGamePageRead(BaseModel):
    items: list[PersonalGameRead]
    total: int
    page: int
    per_page: int
    platforms: list[Platform] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)


class RecentAcquisitionRead(BaseModel):
    participant: ParticipantRead
    game: GameRead
    occurred_at: datetime
    date_kind: Literal["acquired", "first_seen"]
    platforms: list[Platform] = Field(default_factory=list)


class ManualOwnershipCreate(BaseModel):
    participant_id: int
    game_id: int
    platform: Platform


class ManualOwnershipConfirmationRead(BaseModel):
    id: int
    platform: Platform


class ManualOwnershipGameOptionRead(BaseModel):
    id: int
    title: str
    release_date: date | None = None
    owner_count: int = 0
    platforms: list[Platform] = Field(default_factory=list)
    owned: bool = False
    manual_confirmations: list[ManualOwnershipConfirmationRead] = Field(default_factory=list)


class ManualOwnershipRead(BaseModel):
    id: int
    participant_id: int
    game_id: int
    platform: Platform
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)



class GameOwnerRead(BaseModel):
    participant: ParticipantRead
    platforms: list[Platform]
    account_names: list[str]
    total_playtime_minutes: int
    last_seen: datetime | None = None

class RecommendationRead(BaseModel):
    game: GameRead
    owner_count: int
    available_player_count: int
    known_player_count: int
    selected_player_count: int
    coverage_percent: float
    total_playtime_minutes: int
    average_playtime_minutes: float
    median_playtime_minutes: float
    score: float
    platforms: list[Platform]
    owners: list[ParticipantRead]
    unknown_players: list[ParticipantRead]



class MetadataSyncRead(BaseModel):
    scanned_games: int
    updated_games: int
    failed_games: int
    message: str


class SyncRunRead(BaseModel):
    id: int
    account_id: int | None
    participant_id: int | None
    kind: str
    started_at: datetime
    finished_at: datetime | None
    success: bool
    message: str
    imported_games: int
    stage: str
    progress_current: int
    progress_total: int
    model_config = ConfigDict(from_attributes=True)


UsageEventType = Literal[
    "page_view",
    "find_players_search",
    "group_games_search",
]
AnalyticsPeriod = Literal[
    "custom",
    "before_party",
    "party",
    "all",
]


class UsageEventCreate(BaseModel):
    participant_id: int | None = None
    event_type: UsageEventType
    details: dict[str, Any] = Field(default_factory=dict)


class UsageEventRead(BaseModel):
    id: int
    participant_id: int | None
    participant_name: str
    event_type: str
    occurred_at: datetime
    details: dict[str, Any]
    model_config = ConfigDict(from_attributes=True)


class AnalyticsCountRead(BaseModel):
    key: str
    count: int


class AnalyticsDailyRead(BaseModel):
    date: date
    total_events: int
    page_views: int
    find_players_searches: int
    group_games_searches: int


class AnalyticsTopGameRead(BaseModel):
    game_id: int | None = None
    title: str
    searches: int
    unique_users: int


class AnalyticsSelectedPlayerRead(BaseModel):
    participant_id: int | None = None
    nickname: str
    selections: int
    unique_searchers: int


class AnalyticsParticipantRead(BaseModel):
    participant_id: int
    nickname: str
    total_events: int
    page_views: int
    find_players_searches: int
    group_games_searches: int
    last_active_at: datetime


class AnalyticsSummaryRead(BaseModel):
    period: AnalyticsPeriod
    date_from: date
    date_to: date
    total_events: int
    active_users: int
    page_views: int
    find_players_searches: int
    group_games_searches: int
    daily: list[AnalyticsDailyRead]
    event_counts: list[AnalyticsCountRead]
    top_games: list[AnalyticsTopGameRead]
    selected_players: list[AnalyticsSelectedPlayerRead]
    participants: list[AnalyticsParticipantRead]


class AnalyticsParticipantDetailRead(BaseModel):
    participant_id: int
    nickname: str
    date_from: date
    date_to: date
    total_events: int
    event_counts: list[AnalyticsCountRead]
    daily: list[AnalyticsDailyRead]
    top_games: list[AnalyticsTopGameRead]
    recent_events: list[UsageEventRead]


class AnalyticsConfigurationUpdate(BaseModel):
    party_start_at: datetime
    party_end_at: datetime | None = None


class AnalyticsConfigurationRead(BaseModel):
    party_start_at: datetime | None = None
    party_end_at: datetime | None = None


class PrivacyInfoRead(BaseModel):
    controller_name: str
    controller_contact: str
    hosting_provider: str
    analytics_retention_days: int
    access_log_retention_days: int
    backup_retention_days: int
    supervisory_authority: str
    supervisory_authority_url: str




