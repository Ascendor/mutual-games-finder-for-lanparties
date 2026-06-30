from __future__ import annotations

from datetime import date, datetime

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


class GameBase(BaseModel):
    title: str
    description: str = ""
    cover_url: str | None = None
    release_date: date | None = None
    genres: list[str] = Field(default_factory=list)
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


class GameOptionRead(BaseModel):
    id: int
    title: str
    model_config = ConfigDict(from_attributes=True)


class OwnershipCreate(BaseModel):
    participant_id: int
    account_id: int
    game_id: int
    platform: Platform
    playtime_minutes: int = 0
    owned_since: datetime | None = None


class OwnershipRead(OwnershipCreate):
    id: int
    last_seen: datetime
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


class PlayniteImportRead(BaseModel):
    imported_games: int
    skipped_games: int
    created_accounts: int
    updated_ownerships: int
    platforms: list[str]
    message: str

class SyncRunRead(BaseModel):
    id: int
    account_id: int | None
    kind: str
    started_at: datetime
    finished_at: datetime | None
    success: bool
    message: str
    imported_games: int
    model_config = ConfigDict(from_attributes=True)





