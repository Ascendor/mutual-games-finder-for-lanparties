from app import models  # noqa: F401


def test_app_log_entry_endpoint_replaces_old_public_paths(client, db):
    participant = models.Participant(nickname="PlayerTwo")
    db.add(participant)
    db.commit()

    response = client.post(
        "/api/app-log/entries",
        json={
            "participant_id": participant.id,
            "event_type": "page_view",
            "details": {"path": "/"},
        },
    )

    assert response.status_code == 201
    assert response.json()["participant_name"] == "PlayerTwo"
    assert client.post("/api/app-log/events", json={}).status_code == 404
    assert client.post("/api/analytics/entries", json={}).status_code == 404
    assert client.post("/api/analytics/events", json={}).status_code == 404
