# Deployed smoke test

Run manually against the deployed URL after each release.

Deployed worker URL: `https://dealership-inventory-api.moeezz321.workers.dev`

## 1. Health check

```bash
curl -s https://dealership-inventory-api.moeezz321.workers.dev/api/health
# expect: {"status":"ok"}
```

## 2. Login

```bash
curl -s -c cookies.txt -X POST https://dealership-inventory-api.moeezz321.workers.dev/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin1@northgate.test","password":"Passw0rd!"}'
# expect: 200, user profile JSON
```

## 3. Allowed update (admin, own dealership)

```bash
curl -s -b cookies.txt -X PATCH https://dealership-inventory-api.moeezz321.workers.dev/api/vehicles/veh-north-1 \
  -H "Content-Type: application/json" \
  -d '{"make":"Toyota","model":"Camry","year":2022,"status":"sold","version":1}'
# expect: 200, version incremented to 2
```

## 4. Rejected access attempt (viewer tries to edit)

```bash
curl -s -c viewer_cookies.txt -X POST https://dealership-inventory-api.moeezz321.workers.dev/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"viewer1@northgate.test","password":"Passw0rd!"}'

curl -s -b viewer_cookies.txt -X PATCH https://dealership-inventory-api.moeezz321.workers.dev/api/vehicles/veh-north-1 \
  -H "Content-Type: application/json" \
  -d '{"make":"Toyota","model":"Camry","year":2022,"status":"available","version":2}'
# expect: 403
```

## 5. Stale-edit conflict

```bash
# Using the same admin1 session, retry the original stale version=1 payload
curl -s -b cookies.txt -X PATCH https://dealership-inventory-api.moeezz321.workers.dev/api/vehicles/veh-north-1 \
  -H "Content-Type: application/json" \
  -d '{"make":"Toyota","model":"Camry","year":2022,"status":"pending","version":1}'
# expect: 409, current_version in the response body
```

## Results

Run against the live deployment on 2026-10-16:

| Check | Result |
|---|---|
| Health | Pass — `{"status":"ok"}` |
| Login | Pass — 200, returned `{"id":"user-north-admin1","email":"admin1@northgate.test","role":"admin","dealership_id":"dealership-north"}` |
| Allowed update | Pass — 200, `version` incremented from 1 to 2 |
| Rejected access | Pass — viewer PATCH returned 403 |
| Stale-edit conflict | Pass — replaying `version=1` after the update returned `{"detail":{"message":"vehicle was modified by someone else; refresh and retry","current_version":2}}` |
