"""template_render package — PDF rendering engine for government letters.

Public API (backward compatible with the old single-file module):

    from app.services.template_render import TemplateRenderService
"""
from ._base import format_tanggal_indonesia
from .service import TemplateRenderService
from .template_file import TemplateFileService

__all__ = ["TemplateRenderService", "TemplateFileService", "format_tanggal_indonesia"]
