import pytest
from app.core.exceptions import ValidationAppError
from app.services.file_storage import FileStorageService


@pytest.mark.asyncio
async def test_save_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 100})(),
    )
    svc = FileStorageService()
    path = await svc.save(b"hello world", "photo.JPG", subdir="attachments")
    assert path.endswith(".jpg")
    assert await svc.read(path) == b"hello world"


def test_validate_upload_rejects_oversized(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 10, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    with pytest.raises(ValidationAppError):
        svc.validate_upload(b"x" * 11, "image/png")


def test_validate_upload_rejects_bad_mime(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 100, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    with pytest.raises(ValidationAppError):
        svc.validate_upload(b"x", "application/zip")


def test_validate_upload_accepts_allowed_mimes(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 100, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    for mime in ("image/jpeg", "image/png", "application/pdf"):
        svc.validate_upload(b"x", mime)  # must not raise


def test_validate_upload_allow_pdf_false_rejects_pdf(monkeypatch):
    """2026-08-13 (HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md, "Extention Lampiran
    wajib foto tidak bisa file lain"): a letter submission's REQUIRED
    attachments must be a photo, not a PDF."""
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 100, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    with pytest.raises(ValidationAppError):
        svc.validate_upload(b"x", "application/pdf", allow_pdf=False)


def test_validate_upload_allow_pdf_false_still_accepts_images(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 100, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    for mime in ("image/jpeg", "image/png"):
        svc.validate_upload(b"x", mime, allow_pdf=False)  # must not raise
