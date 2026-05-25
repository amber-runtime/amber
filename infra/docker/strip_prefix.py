"""
ASGI middleware to strip a configurable path prefix from incoming requests.
Used when running behind a path-based reverse proxy (ALB/CloudFront).

Usage:
  uvicorn strip_prefix:create_app("admin_control_plane.dashboard_backend:app", "/dashboard") ...
"""

import importlib
import os


def _strip_prefix(app, prefix: str):
    """Return an ASGI app that strips `prefix` from the start of raw_path."""

    async def asgi(scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            raw = scope.get("root_path", "") + scope.get("path", "")
            # Strip prefix from path
            path = scope.get("path", "")
            if path.startswith(prefix):
                scope["path"] = path[len(prefix):] or "/"
                raw_path = scope.get("raw_path", b"")
                scope["raw_path"] = raw_path[len(prefix.encode()):] or b"/"
            scope["root_path"] = prefix
        await app(scope, receive, send)

    return asgi


def create_app(module_path: str, prefix: str):
    """Import an ASGI app and wrap it with prefix stripping."""
    mod_name, attr = module_path.rsplit(":", 1)
    mod = importlib.import_module(mod_name)
    app = getattr(mod, attr)
    return _strip_prefix(app, prefix)


if __name__ == "__main__":
    import uvicorn

    module = os.environ.get("ASGI_APP", "admin_control_plane.dashboard_backend:app")
    prefix = os.environ.get("PATH_PREFIX", "/dashboard")
    port = int(os.environ.get("PORT", "8001"))
    app = create_app(module, prefix)
    uvicorn.run(app, host="0.0.0.0", port=port)
