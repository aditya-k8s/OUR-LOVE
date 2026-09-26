"""Public story pages. Each view has one job; data access lives in services.py."""
from __future__ import annotations

import calendar
from datetime import date

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.core.dates import month_matrix, parse_iso, shift_month, today
from apps.core.registry import CONTENT_TYPES, choice_label
from apps.core.repository import repo
from apps.core.site_settings import get_settings
from apps.media.services import attach_photo_urls, photo_urls, video_src

from . import services

PER_PAGE = 24


def _page(request, key: str, extra: dict | None = None, per_page: int = PER_PAGE, sort=None) -> dict:
    ct = CONTENT_TYPES[key]
    query = services.visible(request, key, extra)
    total = repo(ct.collection).count(query)
    pages = max(1, -(-total // per_page))
    try:
        number = min(max(int(request.GET.get("page", 1)), 1), pages)
    except ValueError:
        number = 1
    items = repo(ct.collection).find(query, sort=sort or ct.default_sort, limit=per_page, skip=(number - 1) * per_page)
    return {
        "items": items,
        "total": total,
        "number": number,
        "pages": pages,
        "has_next": number < pages,
        "has_previous": number > 1,
    }


def _hero_media(request, site: dict) -> dict:
    appearance = site["appearance"]
    photo = video = None
    if appearance.get("hero_photo_id"):
        photo = repo("photos").get(appearance["hero_photo_id"], services.visible(request, "photos"))
    if appearance.get("hero_video_id"):
        video = repo("videos").get(appearance["hero_video_id"], services.visible(request, "videos"))
    return {
        "photo": photo_urls(photo) if photo else None,
        "video": video_src(video) if video else "",
    }


@require_GET
def home(request):
    site = get_settings()
    duration = services.relationship_duration()
    timeline = services.timeline(request, limit=8)
    memories = services.hydrate(request, services.list_visible(request, "memories", limit=6))
    photos = attach_photo_urls(services.list_visible(request, "photos", limit=9))
    context = {
        "hero": _hero_media(request, site),
        "duration": duration,
        "start_date": site["relationship"].get("start_date"),
        "firsts": services.firsts(request),
        "timeline_groups": services.group_by_year_month(timeline),
        "memories": memories,
        "photos": photos,
        "messages_list": services.list_visible(request, "messages", limit=4),
        "places": services.list_visible(request, "places", limit=6),
        "letters": services.list_visible(request, "letters", limit=3),
        "future": services.hydrate(request, services.list_visible(request, "future", limit=8)),
        "stats": services.stats(request),
        "on_this_day": services.on_this_day(request),
        "upcoming": services.upcoming_dates(request),
        "today": today(),
    }
    return render(request, "content/home.html", context)


@require_GET
def story(request):
    filters = services.clean_filters(request.GET)
    events = services.timeline(request, filters)
    return render(
        request,
        "content/story.html",
        {
            "groups": services.group_by_year_month(events),
            "count": len(events),
            "filters": filters,
            "options": services.filter_options(request, "timeline"),
        },
    )


@require_GET
def memories(request):
    filters = services.clean_filters(request.GET)
    page = _page(request, "memories", services.build_filter_query(filters))
    services.hydrate(request, page["items"])
    return render(
        request,
        "content/memories.html",
        {"page": page, "filters": filters, "options": services.filter_options(request, "memories")},
    )


@require_GET
def memory_detail(request, doc_id: str):
    memory = services.get_visible(request, "memories", doc_id)
    if not memory:
        raise Http404
    services.hydrate(request, [memory])
    memory["mood_label"] = choice_label(CONTENT_TYPES["memories"].field_map["mood"].choices, memory.get("mood"))
    return render(request, "content/memory_detail.html", {"memory": memory})


@require_GET
def event_detail(request, doc_id: str):
    event = services.get_visible(request, "timeline", doc_id)
    if not event:
        raise Http404
    services.hydrate(request, [event])
    return render(request, "content/event_detail.html", {"event": event})


@require_GET
def gallery(request):
    tag = (request.GET.get("tag") or "").strip()[:80]
    page = _page(request, "photos", {"tags": tag} if tag else None, per_page=48)
    attach_photo_urls(page["items"])
    return render(
        request,
        "content/gallery.html",
        {"page": page, "tag": tag, "tags": repo("photos").distinct("tags", services.visible(request, "photos"))},
    )


@require_GET
def moments(request):
    page = _page(request, "videos")
    for v in page["items"]:
        v["src"] = video_src(v)
    services.hydrate(request, page["items"])
    return render(request, "content/moments.html", {"page": page})


@require_GET
def letters(request):
    page = _page(request, "letters")
    return render(request, "content/letters.html", {"page": page})


@require_GET
def letter_detail(request, doc_id: str):
    letter = services.get_visible(request, "letters", doc_id)
    if not letter:
        raise Http404
    services.hydrate(request, [letter])
    return render(request, "content/letter_detail.html", {"letter": letter})


@require_GET
def words(request):
    page = _page(request, "messages", per_page=30)
    return render(request, "content/words.html", {"page": page})


@require_GET
def places(request):
    page = _page(request, "places")
    services.hydrate(request, page["items"])
    for place in page["items"]:
        # Exact coordinates are only shown to signed-in users or for public places.
        place["show_map"] = (
            place.get("latitude") is not None
            and place.get("longitude") is not None
            and (request.user.is_authenticated or place.get("is_public"))
        )
    return render(request, "content/places.html", {"page": page})


@require_GET
def gifts(request):
    page = _page(request, "gifts")
    services.hydrate(request, page["items"])
    return render(request, "content/gifts.html", {"page": page})


@require_GET
def calendar_view(request):
    now = today()
    try:
        year = int(request.GET.get("year", now.year))
        month = int(request.GET.get("month", now.month))
        date(year, month, 1)
    except (ValueError, TypeError):
        year, month = now.year, now.month
    year = min(max(year, 1900), 2200)

    by_day: dict[int, list[dict]] = {}
    for doc in services.list_visible(request, "dates"):
        d = parse_iso(doc.get("date"))
        if not d or d.month != month:
            continue
        if d.year == year or (doc.get("recurring_yearly") and d.year <= year):
            by_day.setdefault(d.day, []).append({**doc, "years": year - d.year, "source": "dates"})
    for key in ("timeline", "future"):
        field = CONTENT_TYPES[key].date_field
        for doc in services.list_visible(request, key, {field: {"$regex": f"^{year}-{month:02d}-"}}):
            d = parse_iso(doc.get(field))
            if d:
                by_day.setdefault(d.day, []).append({**doc, "source": key})

    weeks = [[{"date": d, "items": by_day.get(d.day, []) if d else []} for d in week] for week in month_matrix(year, month)]
    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)
    return render(
        request,
        "content/calendar.html",
        {
            "weeks": weeks,
            "year": year,
            "month": month,
            "month_name": calendar.month_name[month],
            "weekdays": [calendar.day_abbr[i] for i in range(7)],
            "prev": {"year": prev_y, "month": prev_m},
            "next": {"year": next_y, "month": next_m},
            "today": now,
            "agenda": [
                (day, items) for day, items in sorted(by_day.items())
            ],
            "upcoming": services.upcoming_dates(request, limit=6),
        },
    )


@require_GET
def future(request):
    items = services.hydrate(request, services.list_visible(request, "future"))
    done = sum(1 for i in items if i.get("completed"))
    return render(request, "content/future.html", {"items": items, "done": done})


@require_GET
def search(request):
    q = (request.GET.get("q") or "").strip()[:100]
    groups = services.search(request, q)
    return render(
        request,
        "content/search.html",
        {"q": q, "groups": groups, "total": sum(len(g.results) for g in groups)},
    )


@require_GET
def more(request):
    return render(request, "content/more.html")
