"""Helpers for quote video file handling."""

import os


def file_extension_for_upload(name: str) -> str:
    ext = (os.path.splitext(name or '')[1] or '.mp4').lower()
    if ext not in ('.mp4', '.webm', '.mov', '.m4v'):
        return '.mp4'
    return ext
