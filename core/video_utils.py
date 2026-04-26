"""Helpers for quote video file handling."""

import os


def video_mime_type_from_path(path: str) -> str:
    ext = (os.path.splitext(path or '')[1] or '.mp4').lower()
    return {
        '.mp4': 'video/mp4',
        '.m4v': 'video/mp4',
        '.webm': 'video/webm',
        '.mov': 'video/quicktime',
    }.get(ext, 'video/mp4')


def file_extension_for_upload(name: str) -> str:
    ext = (os.path.splitext(name or '')[1] or '.mp4').lower()
    if ext not in ('.mp4', '.webm', '.mov', '.m4v'):
        return '.mp4'
    return ext
