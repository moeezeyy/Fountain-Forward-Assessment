"""In-memory stand-in for the Cloudflare D1 binding, backed by sqlite3.

Mirrors the subset of the D1 JS API that app/db.py relies on:
  db.prepare(sql).bind(*params).first() / .all() / .run()
so the FastAPI app can be exercised in plain pytest without the Workers
runtime. This is a test double, not a production code path.
"""

import sqlite3
from pathlib import Path


class _Meta(dict):
    pass


class _AllResult:
    def __init__(self, rows):
        self.results = rows


class _Statement:
    def __init__(self, conn, sql):
        self._conn = conn
        self._sql = sql
        self._params = ()

    def bind(self, *params):
        self._params = params
        return self

    async def first(self):
        cur = self._conn.execute(self._sql, self._params)
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    async def all(self):
        cur = self._conn.execute(self._sql, self._params)
        rows = [dict(r) for r in cur.fetchall()]
        return _AllResult(rows)

    async def run(self):
        cur = self._conn.execute(self._sql, self._params)
        self._conn.commit()
        meta = _Meta(changes=cur.rowcount if cur.rowcount != -1 else 0)
        return type("RunResult", (), {"meta": meta})()


class FakeD1:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        schema = (Path(__file__).resolve().parent.parent / "migrations" / "0001_init.sql").read_text()
        self._conn.executescript(schema)
        self._conn.commit()

    def prepare(self, sql):
        return _Statement(self._conn, sql)

    def execute_script(self, sql: str):
        self._conn.executescript(sql)
        self._conn.commit()
