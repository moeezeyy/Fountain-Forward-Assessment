-- Dealership inventory schema
-- version column on vehicles implements optimistic concurrency control (OCC).

CREATE TABLE IF NOT EXISTS dealerships (
  id   TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id             TEXT PRIMARY KEY,
  dealership_id  TEXT NOT NULL REFERENCES dealerships(id),
  email          TEXT NOT NULL UNIQUE,
  password_hash  TEXT NOT NULL,
  role           TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
  token_version  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS vehicles (
  id             TEXT PRIMARY KEY,
  dealership_id  TEXT NOT NULL REFERENCES dealerships(id),
  make           TEXT NOT NULL,
  model          TEXT NOT NULL,
  year           INTEGER NOT NULL,
  status         TEXT NOT NULL CHECK (status IN ('available', 'sold', 'pending')),
  version        INTEGER NOT NULL DEFAULT 1,
  updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_dealership ON users(dealership_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_dealership ON vehicles(dealership_id);
