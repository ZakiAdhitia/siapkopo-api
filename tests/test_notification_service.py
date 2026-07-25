import pytest

from app.core.exceptions import NotFoundError
from app.services.auth import AuthService
from app.services.notification import LoggingNotificationProvider, NotificationService


@pytest.mark.asyncio
async def test_notify_creates_row_and_calls_provider(seeded_session):
    warga = await AuthService(seeded_session).users.get_by_username("warga")
    sent = {}

    class _Spy(LoggingNotificationProvider):
        def send_email(self, to, subject, body):
            sent["to"], sent["subject"], sent["body"] = to, subject, body

    notif = await NotificationService(seeded_session, provider=_Spy()).notify(
        warga.id, "test:event", "Judul", "Isi pesan", email_to="warga@test.local",
    )
    assert notif.title == "Judul"
    assert notif.is_read is False
    assert sent["to"] == "warga@test.local"


@pytest.mark.asyncio
async def test_notify_without_email_to_does_not_send(seeded_session):
    warga = await AuthService(seeded_session).users.get_by_username("warga")
    sent = {}

    class _Spy(LoggingNotificationProvider):
        def send_email(self, to, subject, body):
            sent["called"] = True

    await NotificationService(seeded_session, provider=_Spy()).notify(
        warga.id, "test:event", "Judul", "Isi",
    )
    assert "called" not in sent


@pytest.mark.asyncio
async def test_list_scoped_to_own_user(seeded_session):
    warga = await AuthService(seeded_session).users.get_by_username("warga")
    staff = await AuthService(seeded_session).users.get_by_username("staf")
    svc = NotificationService(seeded_session)

    await svc.notify(warga.id, "a", "A", "a")
    await svc.notify(staff.id, "b", "B", "b")

    items, total = await svc.list(warga.id, 1, 20)
    assert total == 1
    assert items[0].user_id == warga.id


@pytest.mark.asyncio
async def test_mark_read_and_mark_all_read(seeded_session):
    warga = await AuthService(seeded_session).users.get_by_username("warga")
    svc = NotificationService(seeded_session)
    n1 = await svc.notify(warga.id, "a", "A", "a")
    await svc.notify(warga.id, "b", "B", "b")

    updated = await svc.mark_read(warga.id, n1.id)
    assert updated.is_read is True

    count = await svc.mark_all_read(warga.id)
    assert count == 1  # only the still-unread second one


@pytest.mark.asyncio
async def test_mark_read_rejects_other_users_notification(seeded_session):
    warga = await AuthService(seeded_session).users.get_by_username("warga")
    staff = await AuthService(seeded_session).users.get_by_username("staf")
    svc = NotificationService(seeded_session)
    n1 = await svc.notify(warga.id, "a", "A", "a")

    with pytest.raises(NotFoundError):
        await svc.mark_read(staff.id, n1.id)
