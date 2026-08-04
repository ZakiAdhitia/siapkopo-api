"""WhatsApp delivery via the Fonnte gateway (https://fonnte.com).

Used only for password-reset OTP delivery today -- a separate, narrower
concern from `NotificationProvider` (email), not folded into that
abstraction since nothing else in the system sends WhatsApp messages (see
`app/services/notification.py`'s "no WhatsApp channel exists" note, which
still holds for every OTHER notification -- this is a deliberate, scoped
exception for password reset specifically).
"""
import re

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("whatsapp")


def _normalize_id_phone(phone: str) -> str:
    """Normalize an Indonesian phone number to Fonnte's expected "62..."
    form: strip spaces/dashes, drop a leading "+", and turn a leading "0"
    into "62" (the same "0812..." <-> "62812..." convention already used
    for guest WhatsApp contact numbers, see
    `app/api/v1/public_submission.py::_WHATSAPP_PATTERN`)."""
    digits = re.sub(r"[^\d]", "", phone)
    if digits.startswith("0"):
        return "62" + digits[1:]
    return digits


class WhatsAppProvider:
    """Sends WhatsApp messages through the Fonnte gateway.

    Fails soft (log + return) on missing config or delivery errors, same
    as `LoggingNotificationProvider.send_email` -- a password-reset
    request's response must never reveal whether delivery actually
    succeeded (that would leak account existence/contact info).
    """

    async def send_message(self, to: str, message: str) -> None:
        settings = get_settings()
        if not settings.fonnte_api_key:
            logger.warning("FONNTE_API_KEY belum diset -- pesan WhatsApp tidak dikirim")
            return
        target = _normalize_id_phone(to)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    settings.fonnte_api_url,
                    headers={"Authorization": settings.fonnte_api_key},
                    data={"target": target, "message": message},
                )
            if response.status_code >= 400:
                logger.error(
                    "Fonnte menolak pengiriman WhatsApp target=%s status=%s body=%s",
                    target, response.status_code, response.text[:300],
                )
                return
            logger.info("WhatsApp terkirim via Fonnte target=%s", target)
        except httpx.HTTPError as exc:
            logger.error("Gagal mengirim WhatsApp via Fonnte target=%s: %s", target, exc)
