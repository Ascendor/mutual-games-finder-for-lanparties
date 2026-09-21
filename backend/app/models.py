from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Platform(StrEnum):
    steam = "steam"
    epic = "epic"
    gog = "gog"
    xbox = "xbox"
    ubisoft = "ubisoft"
    ea = "ea"
    amazon = "amazon"
    battle_net = "battle_net"
    bethesda = "bethesda"
    gamejolt = "gamejolt"
    humble = "humble"
    humble_key = "humble_key"
    meta = "meta"
    itch = "itch"
    legacy = "legacy"
    nintendo = "nintendo"
    playstation = "playstation"
    riot = "riot"
    rockstar = "rockstar"
    local = "local"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Participant(TimestampMixin, Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    real_name: Mapped[str | None] = mapped_column(String(180))
    present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    accounts: Mapped[list[Account]] = relationship(back_populates="participant", cascade="all, delete-orphan")
    ownerships: Mapped[list[Ownership]] = relationship(back_populates="participant", cascade="all, delete-orphan")
    manual_ownerships: Mapped[list[ManualOwnership]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )
    usage_events: Mapped[list[UsageEvent]] = relationship(
        back_populates="participant",
        passive_deletes=True,
    )


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform", "account_id", name="uq_account_platform_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[Platform] = mapped_column(String(40), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)

    participant: Mapped[Participant] = relationship(back_populates="accounts")
    ownerships: Mapped[list[Ownership]] = relationship(back_populates="account", passive_deletes=True)
    sync_runs: Mapped[list[SyncRun]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Game(TimestampMixin, Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String(800))
    release_date: Mapped[date | None] = mapped_column(Date)
    genres: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_game: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    non_game_reason: Mapped[str | None] = mapped_column(String(255))
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    singleplayer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    multiplayer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_coop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    online_coop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hotseat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    split_screen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shared_screen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    campaign_coop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drop_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    versus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_players: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_players: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    offline_max_players: Mapped[int | None] = mapped_column(Integer)
    online_max_players: Mapped[int | None] = mapped_column(Integer)
    offline_coop_max_players: Mapped[int | None] = mapped_column(Integer)
    online_coop_max_players: Mapped[int | None] = mapped_column(Integer)
    multiplayer_metadata_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    player_count_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_source: Mapped[str | None] = mapped_column(String(40))
    metadata_external_id: Mapped[str | None] = mapped_column(String(120))
    metadata_sources: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    metadata_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    ownerships: Mapped[list[Ownership]] = relationship(back_populates="game", cascade="all, delete-orphan")
    manual_ownerships: Mapped[list[ManualOwnership]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    mappings: Mapped[list[PlatformGameMapping]] = relationship(back_populates="game", cascade="all, delete-orphan")


class PlatformGameMapping(Base):
    __tablename__ = "platform_game_mappings"
    __table_args__ = (UniqueConstraint("platform", "platform_game_id", name="uq_platform_game"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[Platform] = mapped_column(String(40), nullable=False)
    platform_game_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    game: Mapped[Game] = relationship(back_populates="mappings")


class Ownership(Base):
    __tablename__ = "ownerships"
    __table_args__ = (UniqueConstraint("participant_id", "game_id", "platform", name="uq_owner_game_platform"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[Platform] = mapped_column(String(40), nullable=False)
    playtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    owned_since: Mapped[datetime | None] = mapped_column(DateTime)
    owned_since_source: Mapped[str | None] = mapped_column(String(40))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_seen_is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    participant: Mapped[Participant] = relationship(back_populates="ownerships")
    account: Mapped[Account | None] = relationship(back_populates="ownerships")
    game: Mapped[Game] = relationship(back_populates="ownerships")


class ManualOwnership(Base):
    __tablename__ = "manual_ownerships"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "game_id",
            "platform",
            name="uq_manual_owner_game_platform",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[Platform] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    participant: Mapped[Participant] = relationship(back_populates="manual_ownerships")
    game: Mapped[Game] = relationship(back_populates="manual_ownerships")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40), default="account", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    imported_games: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    progress_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    account: Mapped[Account | None] = relationship(back_populates="sync_runs")


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"),
        index=True,
    )
    participant_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    participant: Mapped[Participant | None] = relationship(back_populates="usage_events")


class AnalyticsConfiguration(Base):
    __tablename__ = "analytics_configuration"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    party_start_at: Mapped[datetime | None] = mapped_column(DateTime)
    party_end_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RecommendationCacheRevision(Base):
    __tablename__ = "recommendation_cache_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
