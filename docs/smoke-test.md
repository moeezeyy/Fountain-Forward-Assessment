# Deployed smoke test

Run manually against the deployed URL after each release. Fill in actual
results once deployed (this file is a template until then).

## 1. Health check

```bash
curl -s https://<worker-url>/api/health
# expect: {"status":"ok"}
```

## 2. Login

```bash
curl -s -c cookies.txt -X POST https://<worker-url>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin1@northgate.test","password":"Passw0rd!"}'
# expect: 200, user profile JSON
```

## 3. Allowed update (admin, own dealership)

```bash
curl -s -b cookies.txt -X PATCH https://<worker-url>/api/vehicles/veh-north-1 \
  -H "Content-Type: application/json" \
  -d '{"make":"Toyota","model":"Camry","year":2022,"status":"sold","version":1}'
# expect: 200, version incremented to 2
```

## 4. Rejected access attempt (viewer tries to edit)

```bash
curl -s -c viewer_cookies.txt -X POST https://<worker-url>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"viewer1@northgate.test","password":"Passw0rd!"}'

curl -s -b viewer_cookies.txt -X PATCH https://<worker-url>/api/vehicles/veh-north-1 \
  -H "Content-Type: application/json" \
  -d '{"make":"Toyota","model":"Camry","year":2022,"status":"available","version":2}'
# expect: 403
```

## 5. Stale-edit conflict

```bash
# Using the same admin1 session, retry the original stale version=1 payload
curl -s -b cookies.txt -X PATCH https://<worker-url>/api/vehicles/veh-north-1 \
  -H "Content-Type: application/json" \
  -d '{"make":"Toyota","model":"Camry","year":2022,"status":"pending","version":1}'
# expect: 409, current_version in the response body
```

## Results

| Check | Result |
|---|---|
| Health | _pending first deployment_ |
| Login | _pending_ |
| Allowed update | _pending_ |
| Rejected access | _pending_ |
| Stale-edit conflict | _pending_ |
