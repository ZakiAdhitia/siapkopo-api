"""Audit log listing endpoint (CLAUDE.md "Logging")."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.audit_log import AuditLogRead
from app.schemas.common import Page, build_page
from app.services.audit_log import AuditLogService

router = APIRouter(prefix="/audit-logs", tags=["audit-log"])


@router.get("", response_model=Envelope[Page[AuditLogRead]])
async def list_audit_logs(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None, description="Cari nama aktor / deskripsi aktivitas"),
    action: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    _=Depends(require_permission("audit:read")),
) -> dict:
    """List audit trail entries, newest first, with search/action/date filters
    (HASIL_UJICOBA_PERROLE.md kades item 8)."""
    items, total = await AuditLogService(session).list(
        page=p.page, size=p.size, search=search, action=action,
        date_from=date_from, date_to=date_to,
    )
    return success_response(build_page(items, total, p.page, p.size, AuditLogRead))
