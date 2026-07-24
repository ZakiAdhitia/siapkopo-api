from app.permissions.registry import PERMISSIONS, ROLE_PERMISSIONS, ROLE_DEFS, DEMO_ACCOUNTS


def test_registry_shapes():
    assert "resident:create" in PERMISSIONS
    assert set(ROLE_PERMISSIONS) == {"warga", "staf", "sekretaris", "kades", "administrator"}
    assert ROLE_PERMISSIONS["administrator"] == ["*"]
    assert {r[0] for r in ROLE_DEFS} == set(ROLE_PERMISSIONS)
    usernames = {a["username"] for a in DEMO_ACCOUNTS}
    assert {"warga", "staf", "sekdes", "kades", "operator"} == usernames


def test_template_permissions_registered():
    assert "template:manage" in PERMISSIONS
    assert "template:read" in PERMISSIONS
    for role in ("staf", "sekretaris", "kades"):
        assert "template:read" in ROLE_PERMISSIONS[role]
