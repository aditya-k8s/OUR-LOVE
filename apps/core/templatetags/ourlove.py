"""Template helpers shared by the public site and the dashboard."""
from __future__ import annotations

import calendar

from django import template
from django.utils.http import urlencode

from apps.core.dates import format_long, parse_iso
from apps.core.registry import CONTENT_TYPES, choice_label

register = template.Library()


@register.filter
def longdate(value) -> str:
    """'2025-07-20' -> '20 July 2025'."""
    return format_long(value)


@register.filter
def shortdate(value) -> str:
    """'2025-07-20' -> '20/07/2025'."""
    d = parse_iso(value)
    return d.strftime("%d/%m/%Y") if d else ""


@register.filter
def daymonth(value) -> str:
    d = parse_iso(value)
    return f"{calendar.month_name[d.month]} {d.day}" if d else ""


@register.filter
def dayonly(value) -> str:
    d = parse_iso(value)
    return str(d.day) if d else ""


@register.filter
def monthabbr(value) -> str:
    d = parse_iso(value)
    return calendar.month_abbr[d.month] if d else ""


@register.filter
def yearof(value) -> str:
    d = parse_iso(value)
    return str(d.year) if d else ""


@register.filter
def get_item(mapping, key):
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None


@register.filter
def field(form, name):
    """{{ form|field:"title" }} -> the bound field."""
    try:
        return form[name]
    except KeyError:
        return None


@register.filter
def label_for(value, spec: str) -> str:
    """{{ doc.category|label_for:"timeline.category" }} -> human label."""
    key, _, field = spec.partition(".")
    ct = CONTENT_TYPES.get(key)
    if not ct or field not in ct.field_map:
        return value or ""
    return choice_label(ct.field_map[field].choices, value)


@register.filter
def location_text(location) -> str:
    if not isinstance(location, dict):
        return ""
    parts = [location.get("name"), location.get("city"), location.get("country")]
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return ", ".join(seen)


@register.filter
def filesize(num) -> str:
    try:
        num = float(num)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs) -> str:
    """Current query string with some parameters replaced (empty value removes)."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    if "page" not in kwargs:
        params.pop("page", None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.simple_tag
def qs(**kwargs) -> str:
    return "?" + urlencode({k: v for k, v in kwargs.items() if v not in (None, "")})


@register.inclusion_tag("partials/icon.html")
def icon(name: str, size: int = 20):
    return {"name": name, "size": size}
