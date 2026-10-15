"""Convert cancel flag, including stopping a running process."""

from __future__ import annotations

import subprocess
import sys

import pytest

from re2_outfit_converter.cancel import (
    raise_if_cancelled,
    request_cancel,
    reset_cancel,
)
from re2_outfit_converter.platform.blender_batch import _wait_blender
from re2_outfit_converter.reports import ConversionCancelled


def test_cancel_flag_raises_and_clears():
    reset_cancel()
    raise_if_cancelled()
    request_cancel()
    with pytest.raises(ConversionCancelled):
        raise_if_cancelled()
    reset_cancel()
    raise_if_cancelled()


def test_wait_blender_kills_process_on_cancel():
    reset_cancel()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    request_cancel()
    try:
        with pytest.raises(ConversionCancelled):
            _wait_blender(proc, 10)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        reset_cancel()
