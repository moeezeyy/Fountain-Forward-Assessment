# Dealership Inventory

Two fictional dealerships sharing one application, with role-scoped access
(admin vs viewer), dealership-scoped data, and optimistic-concurrency
protected vehicle edits. Built for Cloudflare's free tier.

- **Deployed app:** https://dealership-inventory-frontend.moeezz321.workers.dev
- **Deployed API:** https://dealership-inventory-api.moeezz321.workers.dev
- **Successful CI/CD run:** https://github.com/moeezeyy/Fountain-Forward-Assessment/actions/runs/38897507496
- **Video walkthrough:** https://drive.google.com/file/d/14mKeDianwgkIx7obeXNcC6MVKbpWlrtK/view?usp=sharing
- **GitHub repo:** https://github.com/moeezeyy/Fountain-Forward-Assessment

## Reviewer accounts

All seeded accounts share the password `Passw0rd!` (see
[backend/scripts/generate_seed.py](backend/scripts/generate_seed.py)).

| Email | Dealership | Role |
|---|---|---|
| admin1@northgate.test | Northgate Motors | admin |
| admin2@northgate.test | Northgate Motors | admin |
| viewer1@northgate.test | Northgate Motors | viewer |
| admin1@lakeside.test | Lakeside Auto | admin |
| admin2@lakeside.test | Lakeside Auto | admin |
| viewer1@lakeside.test | Lakeside Auto | viewer |

Both Northgate admins (`admin1@northgate.test` / `admin2@northgate.test`)
are provided specifically so reviewers can reproduce the concurrent-edit
scenario against `veh-north-1`.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite, deployed as a **Cloudflare Worker serving static assets** | Small SPA, no SSR needed; Workers' unified static-assets model (`assets.directory` in `wrangler.jsonc`) serves the `dist/` build directly from a `*.workers.dev` URL on the free tier |
| Backend | **Python (FastAPI)** on **Cloudflare Workers (Python, GA)** | Explicitly requested stack; FastAPI is a first-class supported framework for Python Workers |
| Database | **Cloudflare D1** (SQLite) | Free-tier-native, binds directly into the Worker, supports the atomic conditional `UPDATE` the concurrency requirement needs |
| Auth | Hand-rolled HS256 JWT in an httpOnly cookie | Avoids `pyjwt`/`bcrypt` as external dependencies that would need WASM wheels under Pyodide; stdlib `hmac`/`hashlib` only, zero dependency risk |

### Why not a third-party JWT/bcrypt library

Python Workers run on Pyodide. Pure-Python packages work; packages with C
extensions (e.g. `bcrypt`) need a precompiled WASM wheel that may not be
available. To keep deployment reliable, [backend/app/security.py](backend/app/security.py)
implements JWT signing/verification and PBKDF2-SHA256 password hashing
using only the Python standard library (`hmac`, `hashlib`, `base64`,
`json`). This is a deliberate scope-reduction, not an oversight -- it
trades a slightly larger hand-written auth module for zero third-party
native-dependency risk during deployment.

## Architecture

```
frontend/   React + Vite SPA -> Cloudflare Worker (static assets)
backend/    FastAPI app running inside a Python Cloudflare Worker
  app/      FastAPI app: routes, auth, D1 access
  src/      Worker entrypoint (ASGI bridge)
  migrations/  D1 schema + seed data
  tests/    pytest suite (auth, access control, concurrency regression)
```

### Data model

- `dealerships(id, name)`
- `users(id, dealership_id, email, password_hash, role, token_version)`
- `vehicles(id, dealership_id, make, model, year, status, version, updated_at)`

`vehicles.version` is the optimistic-concurrency token. `users.token_version`
is how logout/invalidation works (see below).

## Authentication and authorization

- **Login:** `POST /api/auth/login` verifies the password against a PBKDF2
  hash and sets an httpOnly, `Secure`, `SameSite=Lax` cookie containing a
  signed JWT (`sub`=user id, `tv`=the user's current `token_version`, 30
  minute expiry).
- **Every protected route** decodes the cookie, verifies the HMAC
  signature and expiry, then re-reads the user from D1 and checks that
  `token_version` in the token still matches the DB. This is what makes
  logout actually invalidate the session instead of just deleting a
  cookie the client could resend.
- **Logout:** `POST /api/auth/logout` increments `token_version` in the
  DB. Every previously issued token for that user -- even ones that
  haven't expired -- immediately fails the `token_version` check on its
  next request.
- **Expiry:** JWTs carry a 30 minute `exp` claim; `decode_jwt` rejects
  expired tokens before any DB lookup happens.
- **Role enforcement:** `require_admin()` rejects non-admin writes with
  403 before any DB write is attempted.
- **Dealership scoping:** every query filters by the authenticated user's
  `dealership_id` taken from the verified JWT -- never from a
  client-supplied field. Reading or updating another dealership's vehicle
  returns 403 (never a silent empty result or a 404 that would leak
  existence).

## Concurrency: preventing lost updates

**The requirement:** if two admins load the same vehicle at version N and
both submit edits based on that version, exactly one must succeed and the
other must get a clear conflict -- without a read-then-write race window.

**The implementation** ([backend/app/main.py](backend/app/main.py),
`update_vehicle`): the version check and the write happen in a **single
SQL statement**:

```sql
UPDATE vehicles
SET make = ?, model = ?, year = ?, status = ?, version = version + 1, updated_at = datetime('now')
WHERE id = ? AND dealership_id = ? AND version = ?
```

D1/SQLite executes this as one atomic operation. There is no gap between
"check the version" and "write the row" for a second request to land in.
If the `WHERE` clause doesn't match (because another admin's write already
incremented `version`), `changes == 0` and the request is rejected with
`409`. The 403/404 distinction, and the `current_version` returned to the
client, come from a follow-up `SELECT` -- but that `SELECT` only decides
which error message to show, it plays no role in the accept/reject
decision itself.

### Demonstrated regression (required bug-fix evidence)

The repo's git history is the before/after evidence:

- `eff234c` -- **initial, defective** implementation: `SELECT` the row to
  check existence/ownership, then an **unconditional** `UPDATE` (version
  is incremented but never checked against the client's submitted
  version). This is exactly the read-then-write anti-pattern the spec
  warns against.
- `c47cb6e` -- **fix**: replaces it with the single atomic conditional
  `UPDATE` shown above.

[tests/test_concurrency.py](backend/tests/test_concurrency.py) is
unchanged across both commits. Running it against the defective commit:

```
AssertionError: expected exactly one 200 and one 409, got 200, 200
```

Both concurrent writes silently "succeed" and the second one clobbers the
first -- a real lost update. Full output saved at
[docs/regression-test-against-defective.txt](docs/regression-test-against-defective.txt).

Running the same test against the fix:

```
tests/test_concurrency.py::test_concurrent_edits_from_same_starting_version PASSED
tests/test_concurrency.py::test_stale_edit_after_someone_else_already_updated_is_rejected PASSED
```

Full output at [docs/regression-test-after-fix.txt](docs/regression-test-after-fix.txt).

To reproduce locally:

```bash
cd backend
git show eff234c:backend/app/main.py > /tmp/defective_main.py   # inspect the defective version (pre src/app rename)
python -m pytest tests/test_concurrency.py -v           # run against current (fixed) code
git log --oneline                                        # eff234c (defective) -> c47cb6e (fix)
```

### Reproducing the conflict in the deployed frontend

1. Log in as `admin1@northgate.test` in one browser tab, and
   `admin2@northgate.test` in another (or an incognito window).
2. Both click "Edit" on the same vehicle (e.g. the Toyota Camry) while it's
   still at the same version.
3. Submit admin1's change first -- it succeeds.
4. Submit admin2's change -- the UI shows a conflict banner: "This vehicle
   was updated by someone else... Refresh to see the latest version before
   retrying," with a Refresh button that reloads the current server state.

## QA strategy

- **Backend (pytest, 15 tests):** auth (valid/invalid login, missing/garbage
  token, expiry via `token_version` bump on logout), access control (viewer
  write rejection, cross-dealership read/write rejection, rejected writes
  leave data unchanged), and the concurrency regression above.
  Tests run against the real FastAPI app with a `FakeD1` test double
  ([backend/tests/fake_d1.py](backend/tests/fake_d1.py)) -- an in-memory
  SQLite connection that mirrors D1's `prepare().bind().first()/.all()/.run()`
  API, so the actual route/auth/SQL code under test is unchanged whether it
  runs in CI or on a real Worker.
- **Frontend (Vitest + Testing Library, 1 test):**
  [frontend/src/test/App.test.jsx](frontend/src/test/App.test.jsx) covers
  login -> dealership-scoped inventory display -> an allowed admin update,
  against a mocked `fetch`.
- **Deployed smoke test:** see `docs/smoke-test.md` (to be filled in after
  the first real deployment) covering login, an allowed update, a
  rejected access attempt, and a stale-edit conflict against the live URL.

Run everything:

```bash
# backend
cd backend && pip install fastapi pydantic pytest httpx && python -m pytest -v

# frontend
cd frontend && npm ci && npm test && npm run build
```

## Local setup

### Backend

Dependencies for the Worker itself (FastAPI, pydantic) are declared in
`pyproject.toml` and vendored by `pywrangler`, not installed with pip --
Cloudflare's Python Workers runtime requires this (see "Why pywrangler,
not plain wrangler" below). `pip install fastapi pydantic` is only needed
locally so `pytest` can import the same code outside the Worker runtime.

```bash
cd backend
pip install fastapi pydantic pytest httpx   # for running pytest locally
cp .dev.vars.example .dev.vars   # fill in JWT_SECRET for local wrangler dev
npx wrangler d1 create dealership-db        # one-time; copy the printed database_id into wrangler.toml
npx wrangler d1 migrations apply dealership-db --local
python scripts/generate_seed.py              # regenerate migrations/0002_seed.sql if needed
npx wrangler d1 migrations apply dealership-db --local
uvx --from workers-py pywrangler dev
```

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `JWT_SECRET` | Worker secret (`wrangler secret put JWT_SECRET`), or `.dev.vars` locally | Signs/verifies session JWTs. **Never commit.** |
| `ALLOWED_ORIGIN` | `wrangler.toml` `[vars]` or secret | CORS allow-list for the deployed frontend origin |
| `VITE_API_BASE_URL` | Frontend build-time env / GitHub secret | Backend API origin the SPA calls |

See [backend/.dev.vars.example](backend/.dev.vars.example) and
[frontend/.env.example](frontend/.env.example).

## Cloudflare deployment

1. **D1:** `wrangler d1 create dealership-db`, paste the returned
   `database_id` into `backend/wrangler.toml`, then
   `wrangler d1 migrations apply dealership-db --remote` to create the
   schema and load seed data.
2. **Backend Worker:** `wrangler secret put JWT_SECRET` once (persists
   across deploys, not re-set by CI), then `uvx --from workers-py
   pywrangler deploy` from `backend/`.
3. **Frontend Worker:** build with `VITE_API_BASE_URL` pointed at the
   deployed backend Worker URL, then `wrangler deploy` from `frontend/`
   (it serves the `dist/` build as static assets per `wrangler.jsonc` --
   this is a Worker, not a Pages project, so it must be `wrangler deploy`,
   not `wrangler pages deploy`).
4. **Health check:** `GET /api/health` returns `{"status": "ok"}` and
   exposes no configuration or secrets -- used both as a manual check and
   in the CI deploy job.
5. **First-time workers.dev subdomain:** Cloudflare requires registering a
   `<name>.workers.dev` subdomain on the account before any Worker can go
   live (Dashboard -> Workers & Pages -> Account details -> Subdomain).
   This is a one-time, account-level, interactive step -- it can't be
   scripted from CI.

### Why `pywrangler`, not plain `wrangler`

Plain `wrangler deploy` with a `requirements.txt` only runs that Worker
*locally* (`wrangler dev`) -- it refuses to deploy a Python Worker that
way. Cloudflare's supported path for installing real PyPI packages (like
FastAPI) into a deployed Python Worker is `pywrangler`, driven by
`pyproject.toml`: it resolves dependencies, vendors compatible wheels
into the Worker bundle, and then proxies to `wrangler` for the actual
upload. `pywrangler` itself is installed on demand via `uv`/`uvx`
(`uvx --from workers-py pywrangler <command>`), so no extra tool needs to
be pre-installed in CI beyond `uv`.

A second, unrelated gap surfaced once FastAPI was actually bundled and
running: Cloudflare's Pyodide build does not expose
`hashlib.pbkdf2_hmac` (it's backed by OpenSSL's `_hashlib` bindings,
which this sandboxed runtime omits). `backend/src/app/security.py`
implements PBKDF2-HMAC-SHA256 directly on top of `hmac`/`hashlib.sha256`
instead, with a reduced iteration count (2,000, down from a more typical
390,000+) so the pure-Python loop fits inside the Workers free plan's
hard 10ms CPU-time budget per request -- documented inline and in "Known
limitations" below.

## CI/CD ([.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml))

- **On every PR:** `backend-test` (pytest) and `frontend-test` (Vitest +
  `vite build`) run independently.
- **On push to `main`:** the same two jobs run again, and a `deploy` job
  runs only if both succeed (`needs: [backend-test, frontend-test]`). If
  either required check fails, GitHub Actions skips `deploy` entirely --
  there is no path from a red build to a live deployment.
- **Secrets** (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
  `VITE_API_BASE_URL`, `API_HEALTH_URL`) live in GitHub Actions repository
  secrets, never in source.

### Release recovery

If a deployment on `main` turns out to be broken:

1. **Backend:** `wrangler rollback` restores the previous Worker version
   (Cloudflare keeps prior deployments). Alternatively, revert the bad
   commit on `main` and let the pipeline redeploy the last-known-good
   state.
2. **Frontend:** same mechanism as the backend -- it's also a Cloudflare
   Worker (serving static assets), so `wrangler rollback` or a
   revert-and-redeploy of the last-known-good commit restores it.
3. **Database:** D1 schema migrations in this project are additive
   (`CREATE TABLE IF NOT EXISTS`), so rolling back code doesn't require a
   matching down-migration for the current schema. If a future migration
   changes column types or drops data, a rollback would be limited to
   restoring from a `wrangler d1 export` backup taken before that
   migration -- this project does not yet automate that backup step,
   which is a known limitation.

## Known limitations / unfinished

- No frontend test runs against a live/staging backend in CI (it uses a
  mocked `fetch`); the deployed smoke test (`docs/smoke-test.md`) is the
  manual substitute for a true e2e run against the live URL.
- Create/delete vehicle endpoints are intentionally not implemented
  (explicitly optional per the spec).
- No automated D1 backup/rollback step in CI; see "Release recovery"
  above.
- Python Workers have higher cold-start latency than JS Workers; acceptable
  for this demo's scale, called out here rather than left silent.
- Password hashing uses only 2,000 PBKDF2 iterations (see "Why
  `pywrangler`, not plain wrangler" above) instead of the ~390,000+
  normally recommended, because Cloudflare's Pyodide runtime lacks
  OpenSSL-backed `pbkdf2_hmac` and the free plan hard-caps CPU time at
  10ms/request, leaving no budget for a slower pure-Python KDF loop at a
  stronger iteration count. Acceptable for this synthetic-data assessment;
  would need a paid plan (higher CPU budget) or an edge-native KDF binding
  for production use with real credentials.
