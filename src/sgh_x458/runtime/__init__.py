"""Shared SGH-X458 firmware runtime and desktop adapters."""

import lzma
import sys


def read_asset(path):
    """Read a bundled asset. The single-file build stores large ones xz-compressed as <name>.xz."""
    packed = path.with_name(path.name + ".xz")
    if getattr(sys, "frozen", False) and packed.is_file():
        return lzma.decompress(packed.read_bytes())
    return path.read_bytes()
