"""Supabase Storage REST API (upload + signed URLs) using stdlib only."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def is_storage_configured() -> bool:
    return bool(
        (settings.SUPABASE_URL or '').strip()
        and (settings.SUPABASE_SERVICE_ROLE_KEY or '').strip()
    )


def _auth_headers() -> dict[str, str]:
    key = settings.SUPABASE_SERVICE_ROLE_KEY or ''
    return {
        'Authorization': f'Bearer {key}',
        'apikey': key,
    }


def _encode_object_path(path: str) -> str:
    """Encode each path segment for the Supabase object URL path."""
    parts = [p for p in path.split('/') if p]
    return '/'.join(urllib.parse.quote(p, safe='') for p in parts)


def upload_quote_video(*, file_bytes: bytes, object_path: str, content_type: str) -> None:
    """
    Upload bytes to the quote-videos bucket. Uses upsert to replace an object at the same path.
    """
    if not is_storage_configured():
        raise RuntimeError('Supabase Storage is not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).')
    base = (settings.SUPABASE_URL or '').rstrip('/')
    bucket = settings.SUPABASE_QUOTE_VIDEOS_BUCKET
    enc = _encode_object_path(object_path)
    url = f'{base}/storage/v1/object/{urllib.parse.quote(bucket)}/{enc}'
    req = urllib.request.Request(
        url,
        data=file_bytes,
        method='POST',
        headers={
            **_auth_headers(),
            'Content-Type': content_type,
            'x-upsert': 'true',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            if resp.status not in (200, 201):
                body = resp.read()
                raise RuntimeError(f'Upload failed: HTTP {resp.status} {body!r}')
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='replace')
        logger.error('Supabase upload HTTP %s: %s', e.code, err)
        raise RuntimeError(f'Video upload failed ({e.code}).') from None


def create_signed_video_url(object_path: str, expires_in: int = 600) -> str | None:
    """
    Return a time-limited URL to read a private object, or None if not configured.
    """
    if not is_storage_configured() or not object_path:
        return None
    base = (settings.SUPABASE_URL or '').rstrip('/')
    bucket = settings.SUPABASE_QUOTE_VIDEOS_BUCKET
    enc = _encode_object_path(object_path)
    url = f'{base}/storage/v1/object/sign/{urllib.parse.quote(bucket)}/{enc}'
    payload = json.dumps({'expiresIn': expires_in}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        method='POST',
        headers={**_auth_headers(), 'Content-Type': 'application/json; charset=utf-8'},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='replace')
        logger.error('Supabase sign HTTP %s: %s', e.code, err)
        return None

    signed = data.get('signedURL') or data.get('signedUrl')
    if not signed:
        return None
    if signed.startswith('http://') or signed.startswith('https://'):
        return signed
    if signed.startswith('/'):
        return f'{base}{signed}'
    return f'{base}/storage/v1{signed}'
