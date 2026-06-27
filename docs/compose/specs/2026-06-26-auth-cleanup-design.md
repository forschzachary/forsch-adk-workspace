# Auth Cleanup Design

Date: 2026-06-26
Status: Approved

## [S1] Problem

The auth system has three layers: `X-Graph-Secret`, `X-Frappe-CSRF-Token`, and `sessionStorage`. The Frappe CSRF layer is only needed when the page is loaded inside a Frappe iframe, which is not the primary use case. This creates confusion about which auth mechanism is active.

## [S2] Solution

Drop all Frappe CSRF code. Keep `X-Graph-Secret` as the sole auth mechanism for all mutating endpoints.

### Remove
- `csrfHeaders()` function from `index.html`
- All `X-Frappe-CSRF-Token` references
- `window.frappe?.csrf_token` checks
- `window.frappe?.session?.user` (fallback to `'graph-ui'`)

### Keep
- `graphSecretHeaders()` → `X-Graph-Secret` header
- `mutationHeaders()` → simplified to just `graphSecretHeaders()` + extra
- `sessionStorage` persistence
- `/graph-secret` auto-unlock endpoint
- `ensureGraphSecret()` prompt flow
- All mutating endpoint guards (`_check_secret()`) in `serve.py`

## [S3] Implementation

### `index.html`
1. Remove `csrfHeaders()` function (lines 659-667)
2. Simplify `mutationHeaders()` to `{ ...graphSecretHeaders(), ...extra }`
3. Remove `csrfHeaders()` from `mutationHeaders()` spread
4. Update chat principal fallback from `window.frappe?.session?.user` to `'graph-ui'`

### `serve.py`
No changes — `_check_secret()` already only checks `X-Graph-Secret`.

## [S4] Verification
1. `python3 -m pytest -q` passes
2. Local preview with `GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898`
3. Unlock edits, verify mutations work
4. Verify chat still works
