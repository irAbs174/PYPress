"""Reading Time — estimate minutes-to-read and expose it to public templates."""

from __future__ import annotations

import re


WORDS_PER_MINUTE = 200
TAG_RE = re.compile(r"<[^>]+>")


def estimate_minutes(body: str) -> int:
    text = TAG_RE.sub(" ", body or "")
    words = [part for part in text.split() if part.strip()]
    if not words:
        return 1
    return max(1, round(len(words) / WORDS_PER_MINUTE))


def register(app, hooks):
    def add_reading_time(context, request):
        context = dict(context)
        item = context.get("item")
        if item is not None and getattr(item, "content_type", None) == "post":
            minutes = estimate_minutes(getattr(item, "body", "") or "")
            context["reading_time_minutes"] = minutes
            context["reading_time_label"] = f"{minutes} min read"
        return context

    hooks.add_filter("public.before_render", add_reading_time)
