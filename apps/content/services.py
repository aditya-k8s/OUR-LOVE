"""Read-side services for the public story pages.

All queries go through `visible()` so anonymous visitors (public mode) only
ever receive documents explicitly marked public.
"""
from __future__ import annotations

import calendar
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date

from apps.core.dates import duration_between, parse_iso, today, years_ago_label
from apps.core.registry import CONTENT_TYPES, FIRST_KEYS, ContentType, get_content_type
from apps.core.repository import regex_contains, repo, visibility_filter
from apps.core.site_settings import get_settings
from apps.media.services import attach_photo_urls, video_src


def visible(request, key: str, extra: dict | None = None) -> dict:
    ct = get_content_type(key)
    query = visibility_filter(request, publishable=ct.publishable if ct else True)
    query.update(extra or {})
    return query


def list_visible(request, key: str, extra: dict | None = None, sort=None, limit: int = 0, skip: int = 0) -> list[dict]:
    ct = CONTENT_TYPES[key]
    return repo(ct.collection).find(visible(request, key, extra), sort=sort or ct.default_sort, limit=limit, skip=skip)


def get_visible(request, key: str, doc_id: str) -> dict | None:
    ct = CONTENT_TYPES[key]
    return repo(ct.collection).get(doc_id, visible(request, key))


# ------------------------------------------------------------------ hydration


def _photos_by_id(request, ids: set[str]) -> dict[str, dict]:
    photos = repo("photos").get_many(list(ids), visible(request, "photos"))
    return {p["id"]: p for p in attach_photo_urls(photos)}


def _videos_by_id(request, ids: set[str]) -> dict[str, dict]:
    videos = repo("videos").get_many(list(ids), visible(request, "videos"))
    for v in videos:
        v["src"] = video_src(v)
    return {v["id"]: v for v in videos}


def hydrate(request, docs: list[dict]) -> list[dict]:
    """Attach photo, video and place objects referenced by id (respecting visibility)."""
    photo_ids: set[str] = set()
    video_ids: set[str] = set()
    place_ids: set[str] = set()
    for d in docs:
        photo_ids.update(d.get("photo_ids") or [])
        for single in ("photo_id", "completion_photo_id", "poster_photo_id"):
            if d.get(single):
                photo_ids.add(d[single])
        video_ids.update(d.get("video_ids") or [])
        if d.get("place_id"):
            place_ids.add(d["place_id"])
    photos = _photos_by_id(request, photo_ids) if photo_ids else {}
    videos = _videos_by_id(request, video_ids) if video_ids else {}
    places = {p["id"]: p for p in repo("places").get_many(list(place_ids), visible(request, "places"))} if place_ids else {}
    for d in docs:
        d["photos"] = [photos[i] for i in d.get("photo_ids") or [] if i in photos]
        d["videos"] = [videos[i] for i in d.get("video_ids") or [] if i in videos]
        for single in ("photo_id", "completion_photo_id", "poster_photo_id"):
            if d.get(single):
                d[single.replace("_id", "")] = photos.get(d[single])
        d["cover"] = d["photos"][0] if d["photos"] else d.get("photo")
        d["place"] = places.get(d.get("place_id") or "")
    return docs


# ------------------------------------------------------------------ timeline


def group_by_year_month(events: list[dict]) -> list[dict]:
    years: "OrderedDict[str, OrderedDict[int, list]]" = OrderedDict()
    undated: list[dict] = []
    for e in events:
        d = parse_iso(e.get("date"))
        if not d:
            undated.append(e)
            continue
        years.setdefault(str(d.year), OrderedDict()).setdefault(d.month, []).append(e)
    grouped = [
        {
            "year": year,
            "months": [
                {"month": m, "name": calendar.month_name[m], "events": evs} for m, evs in months.items()
            ],
        }
        for year, months in years.items()
    ]
    if undated:
        grouped.append({"year": "Undated", "months": [{"month": 0, "name": "", "events": undated}]})
    return grouped


def timeline(request, filters: dict | None = None, limit: int = 0) -> list[dict]:
    events = list_visible(request, "timeline", build_filter_query(filters or {}), limit=limit)
    return hydrate(request, events)


def firsts(request) -> list[dict]:
    events = repo("timeline_events").find(
        visible(request, "timeline", {"first_key": {"$in": [k for k, _ in FIRST_KEYS]}}),
        sort=(("date", 1), ("created_at", 1)),
    )
    hydrate(request, events)
    by_key: dict[str, dict] = {}
    for e in events:
        by_key.setdefault(e["first_key"], e)
    return [{"key": key, "label": label, "event": by_key.get(key)} for key, label in FIRST_KEYS]


# ------------------------------------------------------------------ filtering

FILTER_KEYS = ("year", "month", "category", "person", "location", "importance", "tag")


def clean_filters(params) -> dict:
    out = {}
    for key in FILTER_KEYS:
        value = (params.get(key) or "").strip()[:80]
        if value:
            out[key] = value
    if "year" in out and not re.fullmatch(r"\d{4}", out["year"]):
        out.pop("year")
    if "month" in out and not (out["month"].isdigit() and 1 <= int(out["month"]) <= 12):
        out.pop("month")
    return out


def build_filter_query(filters: dict) -> dict:
    query: dict = {}
    year, month = filters.get("year"), filters.get("month")
    if year and month:
        query["date"] = {"$regex": f"^{year}-{int(month):02d}-"}
    elif year:
        query["date"] = {"$regex": f"^{year}-"}
    elif month:
        query["date"] = {"$regex": f"^\\d{{4}}-{int(month):02d}-"}
    if filters.get("category"):
        query["category"] = filters["category"]
    if filters.get("importance"):
        query["importance"] = filters["importance"]
    if filters.get("tag"):
        query["tags"] = filters["tag"]
    if filters.get("person"):
        query["people"] = filters["person"]
    if filters.get("location"):
        rx = regex_contains(filters["location"])
        query["$or"] = [{"location.name": rx}, {"location.city": rx}, {"location.country": rx}]
    return query


def filter_options(request, key: str) -> dict:
    ct = CONTENT_TYPES[key]
    col = repo(ct.collection)
    base = visible(request, key)
    dates = col.distinct("date", base)
    return {
        "years": sorted({d[:4] for d in dates if isinstance(d, str) and len(d) >= 4}, reverse=True),
        "months": [(i, calendar.month_name[i]) for i in range(1, 13)],
        "categories": [c for c in ct.field_map["category"].choices if c[0]] if "category" in ct.field_map else [],
        "people": col.distinct("people", base),
        "tags": col.distinct("tags", base),
        "cities": col.distinct("location.city", base),
        "importance": ct.field_map["importance"].choices if "importance" in ct.field_map else (),
    }


# ------------------------------------------------------------------ stats


def relationship_duration():
    start = parse_iso(get_settings()["relationship"].get("start_date"))
    return duration_between(start, today()) if start else None


def stats(request) -> list[dict]:
    duration = relationship_duration()

    def count(key: str, extra: dict | None = None) -> int:
        return repo(CONTENT_TYPES[key].collection).count(visible(request, key, extra))

    items = [
        {"label": "Days together", "value": duration.total_days if duration else None},
        {"label": "Memories", "value": count("memories")},
        {"label": "Moments on the timeline", "value": count("timeline")},
        {"label": "Photos", "value": count("photos")},
        {"label": "Places", "value": count("places")},
        {"label": "Letters", "value": count("letters")},
        {"label": "Milestones", "value": count("timeline", {"category": "milestone"})},
        {"label": "Dreams completed", "value": count("future", {"completed": True})},
    ]
    return items


# ------------------------------------------------------------------ on this day

ON_THIS_DAY_SOURCES = ("timeline", "memories", "letters", "messages", "dates", "gifts", "places")


def on_this_day(request, on: date | None = None) -> list[dict]:
    on = on or today()
    pattern = {"$regex": f"^\\d{{4}}-{on.month:02d}-{on.day:02d}$"}
    results: list[dict] = []
    for key in ON_THIS_DAY_SOURCES:
        ct = CONTENT_TYPES[key]
        for doc in repo(ct.collection).find(visible(request, key, {"date": pattern})):
            d = parse_iso(doc.get("date"))
            if not d or d > on:
                continue
            if d.year == on.year and key != "dates":
                continue
            results.append(
                {
                    "kind": ct.label,
                    "key": key,
                    "doc": doc,
                    "title": doc.get(ct.title_field) or ct.label,
                    "date": doc.get("date"),
                    "ago": years_ago_label(d, on),
                    "years": on.year - d.year,
                }
            )
    results.sort(key=lambda r: r["date"])
    return results


def upcoming_dates(request, limit: int = 4) -> list[dict]:
    """Next occurrences of yearly important dates, soonest first."""
    now = today()
    upcoming = []
    for doc in list_visible(request, "dates"):
        d = parse_iso(doc.get("date"))
        if not d:
            continue
        if doc.get("recurring_yearly"):
            try:
                nxt = d.replace(year=now.year)
            except ValueError:  # 29 February
                nxt = date(now.year, 3, 1)
            if nxt < now:
                try:
                    nxt = d.replace(year=now.year + 1)
                except ValueError:
                    nxt = date(now.year + 1, 3, 1)
        else:
            nxt = d
        if nxt >= now:
            upcoming.append({**doc, "next_date": nxt.isoformat(), "in_days": (nxt - now).days})
    upcoming.sort(key=lambda x: x["next_date"])
    return upcoming[:limit]


# ------------------------------------------------------------------ search

SEARCH_SOURCES = ("memories", "timeline", "photos", "videos", "messages", "letters", "places", "gifts", "dates", "future")


@dataclass
class SearchGroup:
    content_type: ContentType
    results: list[dict]


def search(request, q: str, per_type: int = 20) -> list[SearchGroup]:
    q = (q or "").strip()[:100]
    if len(q) < 2:
        return []
    rx = regex_contains(q)
    groups: list[SearchGroup] = []
    for key in SEARCH_SOURCES:
        ct = CONTENT_TYPES[key]
        fields = ct.searchable_fields
        if not fields:
            continue
        query = visible(request, key, {"$or": [{f: rx} for f in fields]})
        docs = repo(ct.collection).find(query, sort=ct.default_sort, limit=per_type)
        if key == "photos":
            attach_photo_urls(docs)
        else:
            hydrate(request, docs)
        if docs:
            groups.append(SearchGroup(ct, docs))
    return groups
