"""Local-disk file storage, behind an interface swappable for object storage
(Cloudflare R2) later without touching any caller."""
import io
import uuid
from pathlib import Path

import aiofiles
from PIL import Image, ImageFilter, ImageStat

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger

logger = get_logger("file_storage")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}
_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}

# Edge-variance (Laplacian-style, via PIL's FIND_EDGES filter) below this is
# treated as "too blurry to verify" -- Bagian 6, STRATEGI doc rev.
# 2026-07-26 anti-fraud requirement: a guest-submitted KTP/KK photo must
# actually be legible for staff to check, not just present. Calibrated
# against a synthetic sharp-text image (variance ~9200) vs the same image
# Gaussian-blurred (variance drops to ~300-400 once visibly blurry) -- this
# is a heuristic default, not a precise measurement, and may need tuning
# against real submitted photos once in production.
_BLUR_VARIANCE_THRESHOLD = 500.0


class FileStorageService:
    """Saves/reads files on local disk under a configurable base directory."""

    def validate_upload(self, content: bytes, content_type: str) -> None:
        """Raise ValidationAppError if the upload violates size/mime rules."""
        settings = get_settings()
        if len(content) > settings.max_upload_size_bytes:
            raise ValidationAppError(
                f"Ukuran file melebihi batas {settings.max_upload_size_bytes // (1024 * 1024)}MB"
            )
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValidationAppError(
                f"Tipe file tidak didukung: {content_type}. "
                "Gunakan JPG, PNG, atau PDF."
            )

    def check_not_blurry(self, content: bytes, content_type: str, document_label: str) -> None:
        """Raise ValidationAppError if a JPEG/PNG photo looks too blurry to
        verify. Skipped for PDF (not a photo) and for any image PIL can't
        decode -- this is a best-effort quality aid for staff, not a hard
        content-format gate (validate_upload already covers that).
        """
        if content_type not in _IMAGE_CONTENT_TYPES:
            return
        try:
            img = Image.open(io.BytesIO(content)).convert("L")
        except Exception:
            return
        edges = img.filter(ImageFilter.FIND_EDGES)
        variance = ImageStat.Stat(edges).var[0]
        if variance < _BLUR_VARIANCE_THRESHOLD:
            raise ValidationAppError(
                f"Foto '{document_label}' terlihat buram, mohon foto ulang yang lebih jelas dan fokus."
            )

    async def save(self, content: bytes, original_filename: str, subdir: str) -> str:
        """Save content under a UUID filename, return the relative storage path."""
        settings = get_settings()
        suffix = Path(original_filename).suffix.lower() or ""
        filename = f"{uuid.uuid4()}{suffix}"
        base = Path(settings.upload_storage_dir) / subdir
        base.mkdir(parents=True, exist_ok=True)
        full_path = base / filename
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        relative = str(Path(subdir) / filename)
        logger.info("File saved subdir=%s filename=%s size=%d", subdir, filename, len(content))
        return relative

    async def read(self, storage_path: str) -> bytes:
        """Read back a previously-saved file by its relative storage path."""
        settings = get_settings()
        full_path = Path(settings.upload_storage_dir) / storage_path
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()
