import re


def slugify(value: str) -> str:
    slug = "-".join(value.strip().lower().split())
    return "".join(ch for ch in slug if ch.isalnum() or ch == "-").strip("-") or "untitled"
