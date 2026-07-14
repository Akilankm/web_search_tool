from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Callable, Iterator

ProgressCallback = Callable[[str, str], None]

_state = threading.local()


@contextmanager
def browser_progress_callback(callback: ProgressCallback) -> Iterator[None]:
    """Bind a job-scoped browser progress callback to the current worker thread."""

    previous = getattr(_state, "callback", None)
    _state.callback = callback
    try:
        yield
    finally:
        if previous is None:
            try:
                delattr(_state, "callback")
            except AttributeError:
                pass
        else:
            _state.callback = previous


def emit_browser_progress(message: str) -> None:
    """Publish browser-candidate progress when running inside an agent job."""

    callback = getattr(_state, "callback", None)
    if callback is not None:
        callback("REQUESTING_BROWSER_EVIDENCE", message)
