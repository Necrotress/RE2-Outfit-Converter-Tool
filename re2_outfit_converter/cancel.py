"""Cooperative cancel flag for a convert running on a background thread."""

from __future__ import annotations

import threading

from .reports import ConversionCancelled

_event = threading.Event()


def reset_cancel() -> None:
    _event.clear()


def request_cancel() -> None:
    _event.set()


def cancel_requested() -> bool:
    return _event.is_set()


def raise_if_cancelled() -> None:
    if _event.is_set():
        raise ConversionCancelled("Convert cancelled.")
