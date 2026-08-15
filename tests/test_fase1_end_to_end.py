"""End-to-end coverage for Fase 1 of ALUR_REVIEW_INPUT_MASTER.md: submit ->
staff fills staff_master_data + staff_extra_data -> approve x2 -> issued,
asserting the domain-master row for every one of the 9 jenis picks up the
right values from the right source (generic block, extra-data sesi, or
citizen answers)."""
import pytest
from sqlalchemy import select

from app.models.auth import Role, User
from app.models.master import MasterPindah, MasterSKU, MasterUbahData
from app.models.submission import Submission, SubmissionStatus
from app.services.letter_template import LetterTemplateService
from app.services.submission import SubmissionService


async def _make_staff_and_warga(session, suffix: str) -> tuple[User, User]:
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    warga = User(username=f"warga_{suffix}", full_name="Warga", hashed_password="x", role_id=roles["warga"].id)
    staff = User(username=f"staff_{suffix}", full_name="Staff", hashed_password="x", role_id=roles["staff"].id)
    session.add_all([warga, staff])
    await session.flush()
    return warga, staff


@pytest.mark.asyncio
async def test_sku_full_flow_uses_generic_block_only(seeded_session):
    """SKU needs zero staff_extra_data -- confirms jenis with source="generic"
    still issue correctly with staff_extra_data left entirely unset."""
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "numbering_prefix": "500", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "jenis_usaha", "label": "Jenis Usaha", "field_type": "text", "is_required": True,
    })
    warga, staff = await _make_staff_and_warga(seeded_session, "sku_e2e")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        warga, template.id, {"jenis_usaha": "Warung Sembako"}, "3516000000000400", "Pemilik Usaha",
    )
    # REQUIRED_STAFF_FIELDS_BY_JENIS["sku"] needs rt_id too -- a real FK.
    from app.models.master import RT, RW
    rw = RW(number="007")
    seeded_session.add(rw)
    await seeded_session.flush()
    rt = RT(rw_id=rw.id, number="002")
    seeded_session.add(rt)
    await seeded_session.flush()
    submission.staff_master_data = {
        "alamat": "Kp. Usaha", "jk": "Laki-laki", "tempat_lahir": "Bogor",
        "tanggal_lahir": "1980-01-01", "pekerjaan": "Wiraswasta", "status_kawin": "Kawin",
        "rt_id": str(rt.id),
    }
    await seeded_session.flush()

    await svc.approve(submission.id, staff, "ok")
    issued = await svc.approve(submission.id, staff, "signed")
    assert issued.status.value == "issued"

    row = (await seeded_session.scalars(
        select(MasterSKU).where(MasterSKU.submission_id == submission.id)
    )).first()
    assert row.jenis_usaha == "Warung Sembako"
    assert row.alamat == "Kp. Usaha"


@pytest.mark.asyncio
async def test_pindah_and_ubah_data_unaffected_by_fase1(seeded_session):
    """Confirms ubah_data (untouched by this phase's rewiring) still issues
    correctly, guarding against an accidental regression elsewhere in
    _save_to_domain_master. Pindah itself WAS later touched (2026-08-13,
    HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md) -- alamat_asal moved from the
    generic staff_master_data.alamat to its own PindahExtraData sesi, so
    this asserts the new source instead of the old one."""
    tsvc = LetterTemplateService(seeded_session)
    pindah_template = await tsvc.create({
        "code": "pindah", "name": "Surat Pindah", "icon": "moving",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "475", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    await tsvc.add_field(pindah_template.id, {
        "field_key": "alamat_tujuan", "label": "Alamat Tujuan", "field_type": "text", "is_required": True,
    })
    warga, staff = await _make_staff_and_warga(seeded_session, "pindah_e2e")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        warga, pindah_template.id, {"alamat_tujuan": "Jl. Baru No. 1"}, "3516000000000500", "Warga Pindah",
    )
    submission.staff_master_data = {"no_kk": "3516000000000501"}
    submission.staff_extra_data = {"alamat_asal": "Kp. Asal", "rt_asal": "003", "rw_asal": "009"}
    await seeded_session.flush()

    await svc.approve(submission.id, staff, "ok")
    await svc.approve(submission.id, staff, "signed")

    row = (await seeded_session.scalars(
        select(MasterPindah).where(MasterPindah.submission_id == submission.id)
    )).first()
    assert row.alamat_tujuan == "Jl. Baru No. 1"
    assert row.alamat_asal == "Kp. Asal"
    assert row.rt_asal == "003"
    assert row.rw_asal == "009"

    ubah_data_template = await tsvc.create({
        "code": "ubah_data", "name": "Perubahan Elemen Data Kependudukan", "icon": "edit_document",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "476", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    for key, label in [("elemen_diubah", "Elemen"), ("data_lama", "Data Lama"), ("data_baru", "Data Baru")]:
        await tsvc.add_field(ubah_data_template.id, {
            "field_key": key, "label": label, "field_type": "text", "is_required": True,
        })
    warga2, staff2 = await _make_staff_and_warga(seeded_session, "ubah_data_e2e")
    # "ubah_data" is deliberately hidden from every submission picker
    # (app/services/letter_template.py _HIDDEN_TEMPLATE_CODES, 2026-08-05
    # product decision predating this plan) -- svc.create() rejects it with
    # NotFoundError by design. That gate only applies to the three creation
    # paths (create/create_guest/create_walkin); svc.approve() has no such
    # check, so build the row directly to exercise the same approve x2 ->
    # _save_to_domain_master path a normal submission would go through.
    ubah_data_submission = Submission(
        template_id=ubah_data_template.id,
        submitted_by_user_id=warga2.id,
        answers={"elemen_diubah": "Pekerjaan", "data_lama": "Petani", "data_baru": "Wiraswasta"},
        applicant_nik="3516000000000600", applicant_nama="Warga Ubah Data",
        status=SubmissionStatus.PENDING, current_step_index=0,
    )
    seeded_session.add(ubah_data_submission)
    await seeded_session.flush()
    ubah_data_submission.staff_master_data = {"alamat": "Kp. Ubah Data", "no_kk": "3516000000000601"}
    await seeded_session.flush()
    await svc.approve(ubah_data_submission.id, staff2, "ok")
    await svc.approve(ubah_data_submission.id, staff2, "signed")

    ubah_data_row = (await seeded_session.scalars(
        select(MasterUbahData).where(MasterUbahData.submission_id == ubah_data_submission.id)
    )).first()
    assert ubah_data_row.elemen_diubah == "Pekerjaan"
    assert ubah_data_row.data_baru == "Wiraswasta"
    assert ubah_data_row.alamat == "Kp. Ubah Data"
