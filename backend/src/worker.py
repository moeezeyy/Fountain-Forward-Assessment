"""Cloudflare Python Worker entrypoint.

Wraps the FastAPI ASGI app so it can run on Cloudflare Workers (Python,
GA). The D1 binding and JWT secret come from the Worker's `env` and are
injected into FastAPI's app.state on every request.
"""

from workers import WorkerEntrypoint
import asgi

from app.main import app, configure


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        configure(self.env.DB, self.env.JWT_SECRET, getattr(self.env, "ALLOWED_ORIGIN", "*"))
        return await asgi.fetch(app, request, self.env)
