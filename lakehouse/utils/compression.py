"""HTML compression helpers for Bronze storage."""

from __future__ import annotations

import zstandard as zstd

_COMPRESSOR = zstd.ZstdCompressor(level=3)
_DECOMPRESSOR = zstd.ZstdDecompressor()


def compress_html(data: bytes | None) -> bytes | None:
    """Compress raw HTML bytes with ZSTD."""
    if data is None:
        return None
    if not data:
        return b""
    return _COMPRESSOR.compress(data)


def decompress_html(data: bytes | None) -> bytes | None:
    """Decompress ZSTD-compressed HTML bytes."""
    if data is None:
        return None
    if not data:
        return b""
    return _DECOMPRESSOR.decompress(data)
