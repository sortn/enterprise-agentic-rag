"""Compatibility ASGI entry point.

The application composition root lives in :mod:`api.application`. Keeping this
small module preserves the familiar ``uvicorn api.main:app`` command without
duplicating routes or constructing a second dependency container.
"""

from .application import app

__all__ = ["app"]
