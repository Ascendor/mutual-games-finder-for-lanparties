from sqlalchemy import select

from app.api.accounts import delete_account
from app.core.config import settings
from app.api.ownerships import (
    create_manual_ownership,
    delete_manual_ownership,
    manual_ownership_options,
)
from app.models import Account, Game, ManualOwnership, Ownership, Participant, Platform, PlatformGameMapping
from app.schemas import ManualOwnershipCreate
from app.services.import_providers import ImportedGame
from app.services.sync_service import _reconcile_account_ownerships, upsert_ownership


def _library(db):
    participant = Participant(nickname="Manual Player")
    game = Game(title="Portal 2", normalized_title="portal 2", multiplayer=True)
    db.add_all([participant, game])
    db.flush()
    db.add(
        PlatformGameMapping(
            game_id=game.id,
            platform=Platform.steam,
            platform_game_id="620",
            platform_title=game.title,
            normalized_title=game.normalized_title,
        )
    )
    db.commit()
    return participant, game


def test_manual_ownership_search_uses_existing_canonical_game(db):
    participant, game = _library(db)

    results = manual_ownership_options(participant.id, "portal", 25, db)

    assert len(results) == 1
    assert results[0]["id"] == game.id
    assert results[0]["platforms"] == [Platform.steam]
    assert results[0]["owned"] is False
    assert db.scalar(select(Game).where(Game.id == game.id)) is game
    assert len(db.scalars(select(Game)).all()) == 1


def test_manual_ownership_is_idempotent_and_creates_effective_ownership(db):
    participant, game = _library(db)
    payload = ManualOwnershipCreate(
        participant_id=participant.id,
        game_id=game.id,
        platform=Platform.steam,
    )

    first = create_manual_ownership(payload, db)
    second = create_manual_ownership(payload, db)

    assert first.id == second.id
    assert len(db.scalars(select(ManualOwnership)).all()) == 1
    ownership = db.scalar(select(Ownership))
    assert ownership is not None
    assert ownership.account_id is None
    assert ownership.game_id == game.id


def test_provider_sync_enriches_and_preserves_manual_ownership(db):
    participant, game = _library(db)
    confirmation = create_manual_ownership(
        ManualOwnershipCreate(
            participant_id=participant.id,
            game_id=game.id,
            platform=Platform.steam,
        ),
        db,
    )
    account = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="76561198000000000",
    )
    db.add(account)
    db.commit()

    ownership = upsert_ownership(
        db,
        account,
        game,
        ImportedGame(
            platform_game_id="620",
            title=game.title,
            playtime_minutes=120,
        ),
    )
    db.flush()
    assert ownership.account_id == account.id
    assert ownership.playtime_minutes == 120

    _reconcile_account_ownerships(db, account, set())
    db.flush()

    assert db.get(Ownership, ownership.id) is not None
    assert db.get(ManualOwnership, confirmation.id) is not None


def test_removing_accountless_manual_ownership_removes_effective_row(db):
    participant, game = _library(db)
    confirmation = create_manual_ownership(
        ManualOwnershipCreate(
            participant_id=participant.id,
            game_id=game.id,
            platform=Platform.steam,
        ),
        db,
    )

    delete_manual_ownership(confirmation.id, db)

    assert db.get(ManualOwnership, confirmation.id) is None
    assert db.scalar(select(Ownership)) is None


def test_deleting_provider_account_keeps_manual_ownership(db):
    participant, game = _library(db)
    account = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="76561198000000001",
    )
    db.add(account)
    db.commit()
    create_manual_ownership(
        ManualOwnershipCreate(
            participant_id=participant.id,
            game_id=game.id,
            platform=Platform.steam,
        ),
        db,
    )
    ownership_id = db.scalar(select(Ownership.id))

    delete_account(account.id, db)

    ownership = db.get(Ownership, ownership_id)
    assert ownership is not None
    assert ownership.account_id is None


def test_deleting_account_removes_stored_provider_credentials(db, tmp_path, monkeypatch):
    participant, _game = _library(db)
    account = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="76561198000000002",
    )
    db.add(account)
    db.commit()
    monkeypatch.setattr(settings, "provider_auth_root", str(tmp_path))
    credentials = tmp_path / "steam" / str(account.id) / "auth.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"refresh_token":"secret"}', encoding="utf-8")

    delete_account(account.id, db)

    assert not credentials.parent.exists()
