from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, POSITION_DEFS, POSITION_PERMISSIONS,
    ROLE_DEFS, ROLE_PERMISSIONS,
)


def test_registry_shapes():
    assert "resident:create" in PERMISSIONS
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
    assert "template:read" in PERMISSIONS
    assert "template:read" in ROLE_PERMISSIONS["staff"]
    assert "template:manage" in ROLE_PERMISSIONS["admin"]


def test_submission_permissions_registered():
    for code in (
        "submission:create", "submission:read", "submission:read_all",
        "submission:approve", "submission:reject", "submission:download",
        "approval_config:manage",
    ):
        assert code in PERMISSIONS
    assert ROLE_PERMISSIONS["warga"] == [
        "auth:me", "submission:create", "submission:read", "submission:download",
    ]
    for role in ("staff", "admin"):
        for code in (
            "submission:read", "submission:read_all", "submission:approve",
            "submission:reject", "submission:download",
        ):
            assert code in ROLE_PERMISSIONS[role]
