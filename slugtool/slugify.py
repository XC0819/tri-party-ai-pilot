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
