"""Render-and-persist a letter template into a standalone file (MASTER_COLUMN_LETTERS.md item 8).

`TemplateRenderService` only renders bytes in memory; this module is the
thin layer above it that (1) fills a template with a submission's real
data, (2) saves the result under a new file in `FileStorageService`, and
returns the storage path so `SubmissionService._issue()` can persist it on
the `Submission` row and hand it to the notification channel once the
letter is approved and ready ("ketika surat sudah siap dan sudah di
approve"). Sub-documents (e.g. NA's 5 documents) go through the same path
so every issued PDF -- not just the main one -- ends up as a saved file
instead of being re-rendered on every download.
"""
from __future__ import annotations

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile
from app.services.file_storage import FileStorageService
from app.services.template_render.service import TemplateRenderService


class TemplateFileService:
    """Fills a template with real data and saves the output as a new file."""

    def __init__(self) -> None:
        self._renderer = TemplateRenderService()
        self._storage = FileStorageService()

    async def render_and_save(
        self, *, template: LetterTemplate, fields: list[TemplateField], profile: VillageProfile,
        answers: dict, applicant: dict, nomor: str, tanggal: str,
    ) -> tuple[bytes, str]:
        """Render the main issued letter and save it as a new file.

        Returns (pdf_bytes, storage_path).
        """
        pdf_bytes = self._renderer.render_issued(
            template=template, fields=fields, profile=profile,
            answers=answers, applicant=applicant, nomor=nomor, tanggal=tanggal,
        )
        storage_path = await self._storage.save(pdf_bytes, f"{template.code}.pdf", subdir="issued")
        return pdf_bytes, storage_path

    async def render_and_save_sub_document(
        self, *, template: LetterTemplate, profile: VillageProfile, answers: dict,
        applicant: dict, nomor: str, tanggal: str, sub_doc_code: str,
    ) -> tuple[bytes, str]:
        """Render one sub-document (e.g. one of NA's 5 documents) and save it
        as its own file. Returns (pdf_bytes, storage_path)."""
        pdf_bytes = self._renderer.render_issued_sub_document(
            template=template, profile=profile, answers=answers, applicant=applicant,
            nomor=nomor, tanggal=tanggal, sub_doc_code=sub_doc_code,
        )
        storage_path = await self._storage.save(pdf_bytes, f"{sub_doc_code}.pdf", subdir="issued")
        return pdf_bytes, storage_path
