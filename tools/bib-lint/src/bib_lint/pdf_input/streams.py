"""Bound every decoded PDF stream, including nested forms, fonts, and object streams."""

import base64
import zlib
from contextlib import contextmanager

from pdfminer.pdftypes import PDFStream, resolve1
from pdfminer.psparser import literal_name


def _bounded_filter(raw, name, remaining):
    if name in ("FlateDecode", "Fl"):
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(raw, remaining + 1)
        if len(decoded) > remaining or decoder.unconsumed_tail:
            raise ValueError("PDF exceeds max_decoded_bytes resource limit")
        return decoded
    if name in ("ASCII85Decode", "A85"):
        return base64.a85decode(raw.strip().removeprefix(b"<~").removesuffix(b"~>"))
    if name in ("ASCIIHexDecode", "AHx"):
        hexadecimal = b"".join(raw.split()).removesuffix(b">")
        if len(hexadecimal) % 2:
            hexadecimal += b"0"
        return bytes.fromhex(hexadecimal.decode("ascii"))
    if name in ("DCTDecode", "DCT", "JPXDecode", "JBIG2Decode"):
        return raw  # pdfminer retains these image formats without expanding their pixels.
    raise ValueError(f"Unsupported PDF content compression: {name}")


def _predictor(parameters, remaining):
    parameters = resolve1(parameters)
    if not isinstance(parameters, dict) or "Predictor" not in parameters:
        return
    values = [
        resolve1(parameters.get(key, default))
        for key, default in (("Colors", 1), ("Columns", 1), ("BitsPerComponent", 8))
    ]
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("Invalid PDF predictor dimensions")
    colors, columns, bits = values
    if colors * columns * bits // 8 > remaining:
        raise ValueError("PDF predictor exceeds max_decoded_bytes resource limit")


def decoded_stream_size(stream, remaining):
    """Check expansion before invoking the library's decoder, without retaining a copy."""
    raw = stream.get_rawdata()
    if raw is None:
        raw = stream.get_data()
    else:
        for compression, parameters in stream.get_filters():
            _predictor(parameters, remaining)
            raw = _bounded_filter(raw, literal_name(compression), remaining)
            if len(raw) > remaining:
                raise ValueError("PDF exceeds max_decoded_bytes resource limit")
    if len(raw) > remaining:
        raise ValueError("PDF exceeds max_decoded_bytes resource limit")
    return len(raw)


@contextmanager
def bounded_streams(maximum):
    """The disposable worker alone wraps the pinned library's central stream decoder."""
    original = PDFStream.decode
    used = 0

    def decode(stream):
        nonlocal used
        if stream.get_rawdata() is None:
            raise ValueError("Invalid undecoded PDF stream")
        size = decoded_stream_size(stream, maximum - used)
        used += size
        if used > maximum:
            raise ValueError("PDF exceeds max_decoded_bytes resource limit")
        return original(stream)

    PDFStream.decode = decode
    try:
        yield
    finally:
        PDFStream.decode = original
