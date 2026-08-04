"""Read-only CRUD services for the per-letter-type domain master tables.

Each service only needs `.list()` (see app/api/v1/domain_master.py) --
these tables are written exclusively by SubmissionService._save_to_domain_master
on issuance, never through this service's `.create()`/`.update()`.
"""
import io

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.models.master import (
    MasterDomisili,
    MasterKelahiran,
    MasterKematian,
    MasterKK,
    MasterNA,
    MasterPindah,
    MasterSKU,
    MasterUbahData,
    MasterUHC,
)
from app.services.master import _CrudService


class MasterDomisiliService(_CrudService):
    model = MasterDomisili
    name = "Master Domisili"

    @property
    def search_columns(self):
        return [MasterDomisili.nik, MasterDomisili.nama]


class MasterKelahiranService(_CrudService):
    model = MasterKelahiran
    name = "Master Kelahiran"

    @property
    def search_columns(self):
        return [MasterKelahiran.nama_anak, MasterKelahiran.nik_ayah, MasterKelahiran.nik_ibu]


class MasterKematianService(_CrudService):
    model = MasterKematian
    name = "Master Kematian"

    @property
    def search_columns(self):
        return [MasterKematian.nik, MasterKematian.nama]


class MasterSKUService(_CrudService):
    model = MasterSKU
    name = "Master SKU"

    @property
    def search_columns(self):
        return [MasterSKU.nik, MasterSKU.nama]


class MasterNAService(_CrudService):
    model = MasterNA
    name = "Master NA"

    @property
    def search_columns(self):
        return [MasterNA.nik, MasterNA.nama, MasterNA.nik_csi]


class MasterUHCService(_CrudService):
    model = MasterUHC
    name = "Master UHC"

    @property
    def search_columns(self):
        return [MasterUHC.nik_pasien, MasterUHC.nama_pasien]


class MasterPindahService(_CrudService):
    model = MasterPindah
    name = "Master Pindah"

    @property
    def search_columns(self):
        return [MasterPindah.nik_pemohon, MasterPindah.nama_pemohon]


class MasterKKService(_CrudService):
    model = MasterKK
    name = "Master KK"

    @property
    def search_columns(self):
        return [MasterKK.no_kk, MasterKK.nama_kk]


class MasterUbahDataService(_CrudService):
    model = MasterUbahData
    name = "Master Ubah Data"

    @property
    def search_columns(self):
        return [MasterUbahData.nik, MasterUbahData.nama]


# jenis (URL-friendly type code) -> service class (HASIL_UJICOBA_PERROLE.md
# kades item 5: "export excel berdasarkan jenis master data").
DOMAIN_MASTER_SERVICES: dict[str, type[_CrudService]] = {
    "domisili": MasterDomisiliService,
    "kelahiran": MasterKelahiranService,
    "kematian": MasterKematianService,
    "sku": MasterSKUService,
    "na": MasterNAService,
    "uhc": MasterUHCService,
    "pindah": MasterPindahService,
    "kk": MasterKKService,
    "ubah_data": MasterUbahDataService,
}

# Internal bookkeeping columns not useful in an exported spreadsheet.
_EXPORT_SKIP_COLUMNS = {"id", "created_at", "updated_at", "deleted_at"}


async def export_domain_master_excel(session: AsyncSession, jenis: str) -> bytes:
    """Export one domain master-data table to xlsx bytes.

    Columns are introspected from the model (`__table__.columns`) rather
    than hand-listed per type -- each of the 9 domain tables has its own
    column set (MASTER_COLUMN_LETTERS.md), and this avoids 9 near-duplicate
    column lists that would silently drift out of sync whenever a model
    gains a field.
    """
    service_cls = DOMAIN_MASTER_SERVICES.get(jenis)
    if service_cls is None:
        raise ValidationAppError(f"Jenis master data tidak dikenal: {jenis}")
    service = service_cls(session)
    items, _ = await service.list(page=1, size=100000)
    columns = [c.name for c in service.model.__table__.columns if c.name not in _EXPORT_SKIP_COLUMNS]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = service.name[:31]
    ws.append(columns)
    for item in items:
        row = []
        for col in columns:
            value = getattr(item, col)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif value is not None and not isinstance(value, (str, int, float, bool)):
                value = str(value)
            row.append(value)
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
