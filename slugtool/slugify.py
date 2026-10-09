"""Utilities for turning titles into URL slugs."""

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Return a lowercase, hyphen-separated slug for *title*.

    Non-alphanumeric runs collapse into a single hyphen; leading and
    trailing hyphens are stripped.
    """
    slug = _NON_ALNUM.sub("-", title.lower())
    return slug.strip("-")


def truncate_slug(slug: str, max_length: int) -> str:
    """Limit a slug's length, preferring the last available hyphen boundary."""
    if max_length <= 0:
        return ""
    if len(slug) <= max_length:
        return slug

    boundary = slug.rfind("-", 0, max_length + 1)
    end = boundary if boundary != -1 else max_length
    return slug[:end].rstrip("-")
