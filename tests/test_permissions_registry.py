from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, POSITION_DEFS, POSITION_PERMISSIONS,
    ROLE_DEFS, ROLE_PERMISSIONS,
)


def test_registry_shapes():
    assert "master_data:read" in PERMISSIONS
    assert set(ROLE_PERMISSIONS) == {"warga", "staff", "admin", "administrator-it"}
    assert ROLE_PERMISSIONS["administrator-it"] == ["*"]
    assert {r[0] for r in ROLE_DEFS} == set(ROLE_PERMISSIONS)
    usernames = {a["username"] for a in DEMO_ACCOUNTS}
    assert {"warga", "staf", "bendahara", "sekdes", "kades", "operator", "rt001", "rw001"} == usernames


def test_position_shapes():
    assert {p[0] for p in POSITION_DEFS} == {
        "kepala_desa", "sekretaris_desa", "bendahara_desa", "staff_desa", "rw", "rt", "warga_desa",
    }
    assert set(POSITION_PERMISSIONS) == {p[0] for p in POSITION_DEFS}
    levels = {slug: level for slug, _, level in POSITION_DEFS}
    assert levels["kepala_desa"] < levels["sekretaris_desa"] < levels["bendahara_desa"]
    assert levels["bendahara_desa"] < levels["staff_desa"] < levels["rw"] < levels["rt"] < levels["warga_desa"]


def test_template_permissions_registered():
    assert "template:manage" in PERMISSIONS
    assert "template:configure" in PERMISSIONS
    assert "template:read" in PERMISSIONS
    assert "template:read" in ROLE_PERMISSIONS["staff"]
    # 2026-08-05 (HASIL_UJICOBA_PERROLE.md sekdes item 1): the "admin" Role
    # (Kepala Desa + Sekretaris Desa) only gets template:configure (toggle
    # active + preview), not full template:manage (create/edit fields).
    assert "template:configure" in ROLE_PERMISSIONS["admin"]
    assert "template:manage" not in ROLE_PERMISSIONS["admin"]


def test_submission_permissions_registered():
    for code in (
        "submission:create", "submission:read", "submission:read_all",
        "submission:approve", "submission:reject", "submission:download",
    ):
        assert code in PERMISSIONS
    for code in ("auth:me", "submission:create", "submission:read", "submission:download"):
        assert code in ROLE_PERMISSIONS["warga"]
    for code in (
        "submission:read", "submission:read_all", "submission:approve",
        "submission:reject", "submission:download",
    ):
        assert code in ROLE_PERMISSIONS["staff"]
    # 2026-08-05 (HASIL_UJICOBA_PERROLE.md kades item 2): the "admin" Role
    # itself only gets read/read_all/download now -- approve/reject move to
    # the Sekretaris Desa Position so Kepala Desa stays view-only.
    for code in ("submission:read", "submission:read_all", "submission:download"):
        assert code in ROLE_PERMISSIONS["admin"]
    for code in ("submission:approve", "submission:reject", "submission:walkin"):
        assert code not in ROLE_PERMISSIONS["admin"]
        assert code not in POSITION_PERMISSIONS["sekretaris_desa"]
