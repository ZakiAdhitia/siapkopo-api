"""Static seed data mirrored from the frontend mockData.js."""

# 2026-08-06: no more Resident population registry (SISTEM_PENGOLAHAN_DATA_WARGA.md)
# -- the RW/RT hierarchy is seeded from this list directly instead of being
# a side effect of iterating resident rows. Decoupled from (but shaped
# identically to) the old RESIDENTS list's (rt, rw) columns: 4 RW numbers,
# each with all 4 RT numbers -- a clean grid, confirmed by inspecting the
# original 36-row list before replacing it.
RW_RT_PAIRS = [
    (rw, rt)
    for rw in ("001", "002", "003", "004")
    for rt in ("001", "002", "003", "004")
]
