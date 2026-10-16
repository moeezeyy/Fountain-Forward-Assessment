"""Thin async wrapper around the Cloudflare D1 binding.

D1 exposes `.prepare(sql).bind(*args)` returning a statement with async
`.first()`, `.all()`, and `.run()` methods. These are JS promises surfaced
to Python via Pyodide FFI, so we simply `await` them here.
"""


async def d1_first(db, sql: str, *params):
    stmt = db.prepare(sql).bind(*params)
    row = await stmt.first()
    if row is None:
        return None
    return dict(row.to_py()) if hasattr(row, "to_py") else dict(row)


async def d1_all(db, sql: str, *params):
    stmt = db.prepare(sql).bind(*params)
    result = await stmt.all()
    results = result.results.to_py() if hasattr(result.results, "to_py") else result.results
    return [dict(r) for r in results]


async def d1_run(db, sql: str, *params):
    """Execute a write statement. Returns the D1 run metadata (changes, etc)."""
    stmt = db.prepare(sql).bind(*params)
    result = await stmt.run()
    meta = result.meta.to_py() if hasattr(result.meta, "to_py") else result.meta
    return dict(meta)
