"""Data-driven RBAC registry: permissions, role mappings, demo accounts."""

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
]

# Role name -> permission codes. "*" means all permissions.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me", "submission:create", "submission:read", "submission:download"],
    "staf": ["auth:me", "resident:read", "resident:create", "resident:update",
             "resident:import", "resident:export", "template:read",
             "submission:read", "submission:read_all", "submission:approve",
             "submission:reject", "submission:download"],
    "sekretaris": ["auth:me", "resident:read", "resident:update",
                   "village:manage", "dusun:manage", "rw:manage", "rt:manage",
                   "family_card:manage", "template:read",
                   "submission:read", "submission:read_all", "submission:approve",
                   "submission:reject", "submission:download"],
    "kades": ["auth:me", "resident:read", "template:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download"],
    "administrator": ["*"],
}

ROLE_DEFS: list[tuple[str, str]] = [
    ("warga", "Warga"),
    ("staf", "Staf Loket"),
    ("sekretaris", "Sekretaris Desa"),
    ("kades", "Kepala Desa"),
    ("administrator", "Admin / Operator"),
]

# Demo accounts mirrored from the frontend mockData.js `accounts` map.
DEMO_ACCOUNTS: list[dict] = [
    {"username": "warga", "password": "warga123", "full_name": "Siti Rohmah",
     "role": "warga", "nik": "3516064588020003"},
    {"username": "staf", "password": "staf123", "full_name": "Nur Aini",
     "role": "staf", "nik": None},
    {"username": "sekdes", "password": "sekdes123", "full_name": "Dewi Lestari",
     "role": "sekretaris", "nik": None},
    {"username": "kades", "password": "kades123", "full_name": "Wiwin Wildan",
     "role": "kades", "nik": None},
    {"username": "operator", "password": "operator123", "full_name": "Operator IT",
     "role": "administrator", "nik": None},
]
