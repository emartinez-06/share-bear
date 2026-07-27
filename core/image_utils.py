"""Downscale/re-encode listing photos so the shop doesn't ship raw phone-camera files."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

# Long enough to look sharp in the detail-page lightbox, short of what a
# modern phone camera produces by default (often 3000-4000px).
MAX_DIMENSION = 1920
JPEG_QUALITY = 85
WEBP_QUALITY = 85

_CONTENT_TYPE_BY_FORMAT = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
}


def resize_for_web(file_bytes: bytes) -> tuple[bytes, str]:
    """
    Downscale an image to MAX_DIMENSION on its longest side and re-encode
    it for web delivery. Respects EXIF orientation (phone photos are often
    stored sideways with an orientation tag) before stripping it. Falls
    back to JPEG for any format other than PNG/WebP.

    Raises PIL.UnidentifiedImageError (via Image.open) if the bytes aren't
    a decodable image - the caller should treat that as a validation
    failure, not a crash.
    """
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)

    fmt = (img.format or 'JPEG').upper()
    if fmt not in _CONTENT_TYPE_BY_FORMAT:
        fmt = 'JPEG'

    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    if fmt == 'JPEG' and img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    buf = io.BytesIO()
    if fmt == 'JPEG':
        img.save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    elif fmt == 'WEBP':
        img.save(buf, format='WEBP', quality=WEBP_QUALITY)
    else:
        img.save(buf, format='PNG', optimize=True)

    return buf.getvalue(), _CONTENT_TYPE_BY_FORMAT[fmt]
