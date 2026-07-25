"""Data-driven RBAC registry: permissions, role/position mappings, demo accounts."""

# Resource:action permission codes. Extend as new features arrive.
PERMISSIONS: list[str] = [
    "auth:me",
    "resident:create", "resident:read", "resident:update", "resident:delete",
    "resident:import", "resident:export",
    "village:manage", "dusun:manage", "rw:manage", "rt:manage", "family_card:manage",
    "template:manage", "template:read",
    "submission:create", "submission:read", "submission:read_all",
    "submission:approve", "submission:reject", "submission:download",
    "approval_config:manage",
    "user:manage",
    "lapduk:manage_own", "lapduk:read_rw", "lapduk:read_all", "lapduk:export", "lapduk:import",
    "notification:read",
]

# Role name -> permission codes. "*" means all permissions.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me", "submission:create", "submission:read", "submission:download",
              "notification:read"],
    "staff": ["auth:me", "resident:read", "resident:create", "resident:update",
              "resident:import", "resident:export", "template:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download",
              "lapduk:read_all", "lapduk:export", "lapduk:import", "notification:read"],
    "admin": ["auth:me", "resident:read", "resident:update",
              "village:manage", "dusun:manage", "rw:manage", "rt:manage", "family_card:manage",
              "template:manage", "template:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download", "approval_config:manage",
              "user:manage", "lapduk:read_all", "lapduk:export", "lapduk:import",
              "notification:read"],
    "administrator-it": ["*"],
}

ROLE_DEFS: list[tuple[str, str]] = [
    ("warga", "Warga"),
    ("staff", "Staff"),
    ("admin", "Admin"),
    ("administrator-it", "Administrator IT"),
]

# Position slug -> (display_name, level). Lower level = higher authority.
POSITION_DEFS: list[tuple[str, str, int]] = [
    ("kepala_desa", "Kepala Desa", 1),
    ("sekretaris_desa", "Sekretaris Desa", 2),
    ("bendahara_desa", "Bendahara Desa", 3),
    ("staff_desa", "Staff Desa", 4),
    ("rw", "RW", 5),
    ("rt", "RT", 6),
    ("warga_desa", "Warga Desa", 7),
]

# Position slug -> permission codes GRANTED IN ADDITION to the user's Role.
# Every slug from POSITION_DEFS must have an entry here, even if empty, so
# seeding can always look it up.
POSITION_PERMISSIONS: dict[str, list[str]] = {
    "kepala_desa": [],
    "sekretaris_desa": [],
    "bendahara_desa": [],
    "staff_desa": [],
    "rw": ["lapduk:read_rw"],
    "rt": ["lapduk:manage_own"],
    "warga_desa": [],
}

# Demo accounts mirrored from the frontend mockData.js `accounts` map, extended
# with the new role/position dimensions. `link_resident_name` (RT/RW accounts
# only) is resolved to a concrete rt_id/rw_id by seed.seed_link_demo_rt_rw
# once master data (RT/RW rows) exists.
DEMO_ACCOUNTS: list[dict] = [
    {"username": "warga", "password": "warga123", "full_name": "Siti Rohmah",
     "role": "warga", "position": "warga_desa", "nik": "3516064588020003",
     "email": "siti.rohmah@example.test"},
    {"username": "staf", "password": "staf123", "full_name": "Nur Aini",
     "role": "staff", "position": "staff_desa", "nik": None,
     "email": "nur.aini@example.test"},
    {"username": "bendahara", "password": "bendahara123", "full_name": "Bambang Sujarwo",
     "role": "staff", "position": "bendahara_desa", "nik": None,
     "email": "bambang.sujarwo@example.test"},
    {"username": "sekdes", "password": "sekdes123", "full_name": "Dewi Lestari",
     "role": "admin", "position": "sekretaris_desa", "nik": None,
     "email": "dewi.lestari@example.test"},
    {"username": "kades", "password": "kades123", "full_name": "Wiwin Wildan",
     "role": "admin", "position": "kepala_desa", "nik": None,
     "email": "wiwin.wildan@example.test"},
    {"username": "operator", "password": "operator123", "full_name": "Operator IT",
     "role": "administrator-it", "position": None, "nik": None,
     "email": "operator.it@example.test"},
    {"username": "rt001", "password": "rt123", "full_name": "Sugeng Riyadi",
     "role": "warga", "position": "rt", "nik": None,
     "email": "sugeng.riyadi@example.test",
     "link_resident_name": "Sugeng Riyadi"},
    {"username": "rw001", "password": "rw123", "full_name": "Ahmad Fauzi",
     "role": "warga", "position": "rw", "nik": None,
     "email": "ahmad.fauzi@example.test",
     "link_resident_name": "Ahmad Fauzi"},
]
