# Letter Template Engine — Security Fix Report: TemplateRenderService SSRF/DoS

**Date:** 2026-07-24
**Branch:** `feat/letter-templates` (local only, no PR)
**File fixed:** `app/services/template_render.py`
**Regression test added:** `tests/test_template_render.py`

## Finding (from B1 whole-branch code review)

`TemplateRenderService.render_preview` called `pisa.CreatePDF(full_html, dest=buffer)`
(xhtml2pdf) with no `link_callback` and no timeout. Plain HTML like
`<img src="http://some-host/path">` in an admin-authored `pdf_body_template` causes
xhtml2pdf to attempt a real outbound network fetch of that URL. No `{{ }}` Jinja
expression is required, so the sandboxed Jinja2 environment (which correctly blocks
template-injection/code-exec attempts) does nothing to stop this — it's plain HTML, not
a template expression.

Impact: SSRF (bounded today — only `template:manage`/administrator can author
templates) and DoS (the render is synchronous; one hanging URL blocks the request for
as long as the remote host takes to respond or time out). `TemplateRenderService` is
the exact function Sub-project B2 will reuse for citizen-triggerable letter issuance,
so closing this now — while template authoring is still admin-only — was judged
cheaper than deferring it.

## Step 1 — Reproducing the vulnerability

Wrote a throwaway script (not committed) rendering a template whose
`pdf_body_template` contained `<img src="http://10.255.255.1/nonexistent">` (a
non-routable IP, chosen so the connection attempt hangs/times out rather than failing
instantly) through the unpatched `TemplateRenderService.render_preview`.

**Result (before fix):** the render took **63.16 seconds** to complete. Log output showed
xhtml2pdf's `NetworkFileUri` making **three separate connection attempts** (its built-in
retry loop), each timing out with `WinError 10060`, before falling back and producing a
PDF with the image simply missing:

```
TimeoutError: [WinError 10060] ... on attempt 1
TimeoutError: [WinError 10060] ... on attempt 2
TimeoutError: [WinError 10060] ... on attempt 3
Could not get image data from src attribute: http://10.255.255.1/nonexistent
Rendered 2091 bytes in 63.16s, starts with %PDF-: True
```

This confirms: (a) a real outbound network attempt is made — the SSRF vector is real —
and (b) it can block a single request for over a minute — the DoS vector is real. Both
independent of any Jinja `{{ }}` expression.

## Step 2 — Investigating xhtml2pdf's resource resolution

Read the installed source at `.venv/Lib/site-packages/xhtml2pdf/`:

- `document.py`: `pisaDocument(..., link_callback=None, ...)` stores the callback as
  `context.pathCallback = link_callback`.
- `context.py:1044`: resource lookups call
  `getFile(name, relative or self.pathDirectory, callback=self.pathCallback)`.
- `files.py`, `pisaFileObject.__init__`:

  ```python
  self.uri: str | Path | None = uri
  self.basepath: str | None = basepath
  if callback and (new := callback(uri, basepath)):
      self.uri = new
      self.basepath = None
  self.instance: BaseFile = FileNetworkManager.get_manager(self.uri, basepath=self.basepath)
  ```

  This is the critical mechanism: **the callback's return value only takes effect if it
  is truthy.** If the callback returns `None`/`""` (falsy), `self.uri` is left as the
  *original* URI and `FileNetworkManager.get_manager` resolves it exactly as it would
  with no callback at all — for an `http(s)://` URI that still means routing to
  `NetworkFileUri` and performing the real network fetch. Returning `None` from
  `link_callback` does **not** block anything — a naive assumption that it would (the
  common "return None to fall back to default resolution" framing in third-party
  examples) is actively wrong for the purpose of blocking a fetch.
- `FileNetworkManager.get_manager` dispatches by scheme: `data:` → `B64InlineURI`
  (pure in-memory, no I/O), `file:` → `LocalProtocolURI`, `http`/`https` →
  `NetworkFileUri` (real socket I/O, 3-attempt retry loop, see
  `NetworkFileUri.get_data`), anything else → `LocalFileURI` (local filesystem read).

Empirically confirmed both branches with a probe script (not committed) against
`pisa.CreatePDF(..., link_callback=...)`:

| Callback behavior | Result |
|---|---|
| Returns a truthy inline `data:` URI | `elapsed=0.02s`, `err=0`, valid PDF — resource silently skipped |
| Raises an exception | Propagates straight out of `pisa.CreatePDF` and **aborts the entire render** — not a graceful degradation |
| Returns `None`/`""` | Same falsy-return code path as no callback — **not** re-measured directly (would cost the same ~63s already measured in Step 1), but confirmed by source reading to be a no-op for blocking purposes |

Conclusion for the fix: the callback must return a **truthy**, purely in-memory `data:`
URI to block a resource — not `None`, and not raise.

## Step 3 — The fix

`app/services/template_render.py`:

1. Added `_block_external_resources(uri, relative)`, a `link_callback` passed to
   `pisa.CreatePDF`. For any URI that is not already an inline `data:` URI, it returns
   `_BLOCKED_RESOURCE_PLACEHOLDER` — a 1x1 transparent GIF `data:` URI — which
   `FileNetworkManager` resolves via `B64InlineURI` (pure in-memory, no filesystem or
   network I/O). Already-inline `data:` URIs are passed through unchanged (no I/O
   either way). This blocks not just `http(s)` fetches but also local-filesystem
   resolution (`LocalFileURI`) as defense-in-depth, since the letter engine's HTML
   (letterhead + admin body) is fully self-contained and never legitimately needs
   either.
2. Wrapped the `pisa.CreatePDF` call with a `socket.setdefaulttimeout(5)` /
   `finally: socket.setdefaulttimeout(previous_timeout)` block as a defense-in-depth
   backstop, in case anything else in the render path could still make a blocking
   socket call. The previous value is restored unconditionally so this never leaks
   into unrelated code elsewhere in the process.
3. `link_callback=_block_external_resources` is passed into the existing
   `pisa.CreatePDF(full_html, dest=buffer)` call; no other behavior of that call
   changed.

## Step 4 — Verifying the fix

Re-ran the Step-1 reproduction script against the patched code:

```
Blocked external resource resolution in letter template render: 'http://10.255.255.1/nonexistent'
Rendered 2469 bytes in 0.07s, starts with %PDF-: True
```

**0.07s**, no network attempt, and the resulting bytes still start with `%PDF-` — the
render still succeeds, just without the blocked image.

## Step 5 — Regression test

Added `test_render_preview_blocks_external_resource_fetch_and_stays_fast` to
`tests/test_template_render.py`: a template body with
`<img src="http://192.0.2.1/nonexistent">` (RFC 5737 TEST-NET-1, a documentation/
non-routable address, so this is deterministic and doesn't depend on real network
reachability at all — the assertion is about wall-clock time being far under any real
network timeout, which only holds because the fetch is never attempted post-fix).
Asserts `elapsed < 2.0` seconds and `pdf_bytes[:5] == b"%PDF-"`.

## Step 6 — No regressions

Confirmed the 11 seeded templates (none use external images) and Bundle D's existing
tests still render identically — see Verification below.

## Verification run

- **Reproduction timing:** before = **63.16s** (3 network retry attempts against a
  non-routable IP); after = **0.07s** (no network attempt, callback short-circuits to
  an inline placeholder). ~900x faster, and now bounded regardless of network
  conditions.
- `pytest tests/test_template_render.py -v` → **4 passed** (3 pre-existing + 1 new
  regression test), 0.10s.
- `pytest tests/test_template_render.py tests/test_letter_template_api.py -v` →
  **7 passed**, 4.87s (only pre-existing `InsecureKeyLengthWarning` warnings, unrelated
  to this change).
- `pytest -q` (full suite) → **70 passed**, 0 failed, 44.31s.
- `ruff check app tests` → **All checks passed!**
- **All 11 seeded templates still render to valid PDFs:** confirmed via a throwaway
  script (not committed) that spins up an in-memory SQLite DB, runs `seed_master` +
  `seed_letter_templates`, and calls `TemplateRenderService.render_preview` for every
  seeded `LetterTemplate` with its real `TemplateField`s and the seeded `Village`.
  Chose the SQLite-seed route (not the live `db_kopo` Postgres DB or the `/preview`
  HTTP endpoint) since it's self-contained, exercises the real seed data end-to-end,
  and needs no Redis/Postgres/auth setup:

  ```
  Seeded templates: 11
    kk                   fields= 3 valid_pdf=True bytes=2539
    domisili             fields= 3 valid_pdf=True bytes=2491
    usaha                fields= 3 valid_pdf=True bytes=2491
    sktm                 fields= 3 valid_pdf=True bytes=2557
    lahir                fields= 3 valid_pdf=True bytes=2525
    mati                 fields= 3 valid_pdf=True bytes=2526
    pindah               fields= 3 valid_pdf=True bytes=2466
    datang               fields= 3 valid_pdf=True bytes=2531
    ktp                  fields= 2 valid_pdf=True bytes=2430
    kkpengantar           fields= 2 valid_pdf=True bytes=2437
    keramaian             fields= 4 valid_pdf=True bytes=2536
  11/11 rendered valid PDFs
  ```

## Files changed

- `app/services/template_render.py`: added `_block_external_resources` link_callback,
  `_BLOCKED_RESOURCE_PLACEHOLDER`, `_RENDER_SOCKET_TIMEOUT_SECONDS`, and wired both
  into `render_preview`'s `pisa.CreatePDF` call with a `socket.setdefaulttimeout`
  try/finally backstop.
- `tests/test_template_render.py`: added
  `test_render_preview_blocks_external_resource_fetch_and_stays_fast`.

No other files modified. No existing behavior removed or weakened.
