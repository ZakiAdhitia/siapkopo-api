"""Data-driven RBAC registry: permissions, role/position mappings, demo accounts."""

# Resource:action permission codes. Extend as new features arrive.
PERMISSIONS: list[str] = [
    "auth:me",
    "resident:create", "resident:read", "resident:update", "resident:delete",
    "resident:import", "resident:export",
    "village:manage", "rw:manage", "rt:manage", "rt:read", "rw:read",
    "family_card:manage",
    "template:manage", "template:configure", "template:read",
    "submission:create", "submission:read", "submission:read_all",
    "submission:approve", "submission:reject", "submission:download", "submission:walkin",
    "approval_config:manage",
    "user:manage",
    "dashboard:read",
    "portal:manage",
    "attendance:create", "attendance:read_all",
    "audit:read",
]

# Role name -> permission codes. "*" means all permissions.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me", "submission:create", "submission:read", "submission:download",
              "template:read"],
    "staff": ["auth:me", "resident:read", "resident:create", "resident:update",
              "resident:import", "resident:export", "template:read", "rt:read", "rw:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download", "submission:walkin",
              "dashboard:read", "attendance:create"],
    # attendance:create, submission:approve/reject/walkin, and
    # approval_config:manage deliberately NOT here -- Kepala Desa and
    # Sekretaris Desa both hold this Role, but HASIL_UJICOBA_PERROLE.md
    # (kades items 2/3/4) restricts Kepala Desa to VIEW-only across
    # submissions, hides Mode Loket, and hides approval-flow config from
    # them entirely; only Sekretaris Desa keeps these, granted per-Position
    # below (same split as attendance:create). submission:read_all/download
    # stay here since Kepala Desa still needs to see and print issued
    # letters, just not approve/reject/walk-in/edit them.
    "admin": ["auth:me", "resident:read", "resident:update",
              "resident:import", "resident:export",
              "village:manage", "rw:manage", "rt:manage", "rt:read", "rw:read",
              "family_card:manage",
              # template:manage (create template, add/edit/delete fields)
              # deliberately NOT here -- HASIL_UJICOBA_PERROLE.md sekdes item 1:
              # only toggling which templates are offered (template:configure)
              # and previewing/reading are allowed from this Role.
              "template:configure", "template:read",
              "submission:read", "submission:read_all", "submission:download",
              "user:manage", "dashboard:read", "portal:manage",
              "attendance:read_all", "audit:read"],
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
    # Level-1 (highest authority) doesn't check in -- only reviews the
    # attendance list (attendance:read_all, granted via the "admin" Role
    # above). Every other position that works from the desa office does.
    "kepala_desa": [],
    "sekretaris_desa": [
        "attendance:create", "submission:approve", "submission:reject",
        "submission:walkin", "approval_config:manage",
    ],
    "bendahara_desa": [],
    "staff_desa": [],
    "rw": [],
    "rt": [],
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
