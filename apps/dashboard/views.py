"""The /admin/ dashboard: overview, generic CRUD, media uploads and settings."""
from __future__ import annotations

import calendar
from collections import Counter

from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.dates import shift_month, today
from apps.core.ratelimit import rate_limit
from apps.core.registry import CONTENT_TYPES, get_content_type
from apps.core.repository import regex_contains, repo
from apps.core.site_settings import get_settings, save_settings
from apps.media import services as media
from apps.media.validation import UploadError, validate_video_url

from . import export
from .decorators import staff_required
from .forms import SettingsForm, build_form, to_document, to_initial

TOGGLEABLE = {"is_published", "is_public", "is_favorite", "completed"}
ADMIN_PER_PAGE = 30


def _ct_or_404(key: str):
    ct = get_content_type(key)
    if not ct:
        raise Http404
    return ct


def _activity_chart(months: int = 12) -> list[dict]:
    """Memories + timeline events per month for the last `months` months (by event date)."""
    now = today()
    keys = [shift_month(now.year, now.month, -i) for i in range(months - 1, -1, -1)]
    first = f"{keys[0][0]}-{keys[0][1]:02d}"
    counts: Counter = Counter()
    for collection in ("memories", "timeline_events"):
        for doc in repo(collection).find({"date": {"$gte": first}}, projection={"date": 1}):
            counts[(doc.get("date") or "")[:7]] += 1
    peak = max(counts.values(), default=0)
    return [
        {
            "label": calendar.month_abbr[m],
            "year": y,
            "value": counts.get(f"{y}-{m:02d}", 0),
            "height": round(100 * counts.get(f"{y}-{m:02d}", 0) / peak) if peak else 0,
        }
        for y, m in keys
    ]


@staff_required
def home(request):
    cards = [
        ("memories", "Memories"),
        ("photos", "Photos"),
        ("videos", "Videos"),
        ("timeline", "Timeline events"),
        ("letters", "Letters"),
        ("places", "Places"),
        ("dates", "Important dates"),
    ]
    stats = [
        {"key": key, "label": label, "value": repo(CONTENT_TYPES[key].collection).count(),
         "url": reverse("dashboard:list", args=[key])}
        for key, label in cards
    ]
    pending = repo("pending_memories").count({"status": "pending"})
    stats.append({"key": "pending", "label": "Pending imports", "value": pending, "url": reverse("imports:index")})
    recent = []
    for key in ("memories", "timeline", "letters", "messages"):
        ct = CONTENT_TYPES[key]
        for doc in repo(ct.collection).find({}, sort=(("updated_at", -1),), limit=5):
            recent.append({"ct": ct, "doc": doc, "title": doc.get(ct.title_field) or "Untitled", "updated": doc.get("updated_at")})
    recent.sort(key=lambda r: r["updated"] or 0, reverse=True)
    site = get_settings()
    checklist = [
        ("Relationship start date", bool(site["relationship"]["start_date"]), reverse("dashboard:settings")),
        ("Names of you both", bool(site["relationship"]["person_one"] and site["relationship"]["person_two"]), reverse("dashboard:settings")),
        ("Hero image", bool(site["appearance"]["hero_photo_id"]), reverse("dashboard:settings")),
        ("How it all started", bool(site["relationship"]["story_intro"]), reverse("dashboard:settings")),
        ("First timeline moment", repo("timeline_events").count() > 0, reverse("dashboard:create", args=["timeline"])),
        ("First photos", repo("photos").count() > 0, reverse("dashboard:list", args=["photos"])),
    ]
    chart = _activity_chart()
    return render(
        request,
        "dashboard/home.html",
        {
            "stats": stats,
            "recent": recent[:8],
            "chart": chart,
            "chart_total": sum(c["value"] for c in chart),
            "checklist": checklist,
            "checklist_done": sum(1 for c in checklist if c[1]),
            "demo_count": sum(repo(ct.collection).count({"is_demo": True}) for ct in CONTENT_TYPES.values()),
        },
    )


@staff_required
def list_view(request, key: str):
    ct = _ct_or_404(key)
    q = (request.GET.get("q") or "").strip()[:100]
    query: dict = {}
    if q and ct.searchable_fields:
        rx = regex_contains(q)
        query["$or"] = [{f: rx} for f in ct.searchable_fields]
    total = repo(ct.collection).count(query)
    pages = max(1, -(-total // ADMIN_PER_PAGE))
    try:
        page = min(max(int(request.GET.get("page", 1)), 1), pages)
    except ValueError:
        page = 1
    sort = (("order", 1), ("created_at", 1)) if ct.orderable else ct.default_sort
    items = repo(ct.collection).find(query, sort=sort, limit=ADMIN_PER_PAGE, skip=(page - 1) * ADMIN_PER_PAGE)
    if key == "photos":
        media.attach_photo_urls(items)
    template = "dashboard/photos.html" if key == "photos" else "dashboard/list.html"
    return render(
        request,
        template,
        {
            "ct": ct,
            "items": items,
            "q": q,
            "total": total,
            "page": page,
            "pages": pages,
            "columns": ct.list_fields,
            "can_reorder": ct.orderable and not q,
        },
    )


def _next_order(collection: str) -> int:
    last = repo(collection).find({}, sort=(("order", -1),), limit=1)
    return int((last[0].get("order") or 0) + 1) if last else 1


def _handle_uploads(request, ct, doc: dict) -> list[str]:
    """Store files uploaded directly from an edit form and attach them to `doc`."""
    errors: list[str] = []
    for spec in ct.fields:
        if spec.kind not in ("photos", "photo"):
            continue
        for upload in request.FILES.getlist(f"{spec.name}__upload")[:30]:
            try:
                photo = media.store_photo(upload, {"date": doc.get("date", ""), "is_public": doc.get("is_public", False)})
            except UploadError as exc:
                errors.append(f"{upload.name}: {exc}")
                continue
            if spec.kind == "photos":
                doc.setdefault(spec.name, [])
                doc[spec.name].append(photo["id"])
            else:
                doc[spec.name] = photo["id"]
    return errors


@staff_required
@require_http_methods(["GET", "POST"])
def edit_view(request, key: str, doc_id: str | None = None):
    ct = _ct_or_404(key)
    existing = None
    if doc_id:
        existing = repo(ct.collection).get(doc_id)
        if not existing:
            raise Http404
    elif not ct.creatable:
        return redirect("dashboard:list", key=key)

    if request.method == "POST":
        form = build_form(ct, data=request.POST)
        if form.is_valid():
            doc = to_document(ct, form.cleaned_data)
            upload_errors = _handle_uploads(request, ct, doc)
            if key == "videos":
                try:
                    doc["external_url"] = validate_video_url(doc.get("external_url", ""))
                except UploadError as exc:
                    form.add_error("external_url", str(exc))
                if not doc.get("external_url") and not (existing and existing.get("storage_key")):
                    form.add_error("external_url", "Add a video link, or upload a file from the Videos page.")
            if key == "future" and doc.get("completed") and not doc.get("completion_date"):
                doc["completion_date"] = today().isoformat()
            if not form.errors:
                if existing:
                    repo(ct.collection).update(doc_id, doc)
                    messages.success(request, f"{ct.label} saved.")
                else:
                    if ct.orderable:
                        doc["order"] = _next_order(ct.collection)
                    repo(ct.collection).insert(doc)
                    messages.success(request, f"{ct.label} added.")
                for err in upload_errors:
                    messages.error(request, err)
                if "save_add" in request.POST:
                    return redirect("dashboard:create", key=key)
                return redirect("dashboard:list", key=key)
    else:
        # New items start empty: dates are never pre-filled so nothing is recorded by accident.
        initial = to_initial(ct, existing) if existing else {"is_published": True}
        form = build_form(ct, initial=initial)

    photo_lookup = {}
    photo_field_names = [s.name for s in ct.fields if s.kind in ("photos", "photo")]
    if photo_field_names:
        photos = media.attach_photo_urls(repo("photos").find({}, sort=(("created_at", -1),), limit=500))
        photo_lookup = {p["id"]: p for p in photos}
    return render(
        request,
        "dashboard/edit.html",
        {
            "ct": ct,
            "form": form,
            "doc": existing,
            "specs": ct.fields,
            "photo_lookup": photo_lookup,
            "photo_preview": media.photo_urls(existing) if key == "photos" and existing else {},
        },
    )


@staff_required
@require_POST
def delete_view(request, key: str, doc_id: str):
    ct = _ct_or_404(key)
    if key == "photos":
        ok = media.delete_photo(doc_id)
    elif key == "videos":
        ok = media.delete_video(doc_id)
    else:
        ok = repo(ct.collection).delete(doc_id)
    if ok:
        messages.success(request, f"{ct.label} deleted.")
    else:
        messages.error(request, "That item no longer exists.")
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"ok": ok})
    return redirect("dashboard:list", key=key)


@staff_required
@require_POST
def toggle_view(request, key: str, doc_id: str, field: str):
    ct = _ct_or_404(key)
    if field not in TOGGLEABLE:
        raise Http404
    doc = repo(ct.collection).get(doc_id)
    if not doc:
        raise Http404
    default = True if field == "is_published" else False
    value = not bool(doc.get(field, default))
    change = {field: value}
    if field == "completed":
        change["completion_date"] = today().isoformat() if value else ""
    repo(ct.collection).update(doc_id, change)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"ok": True, "value": value})
    return redirect(request.POST.get("next") or reverse("dashboard:list", args=[key]))


@staff_required
@require_POST
def reorder_view(request, key: str, doc_id: str, direction: str):
    ct = _ct_or_404(key)
    if not ct.orderable or direction not in ("up", "down"):
        raise Http404
    items = repo(ct.collection).find({}, sort=(("order", 1), ("created_at", 1)), projection={"order": 1})
    ids = [i["id"] for i in items]
    if doc_id not in ids:
        raise Http404
    idx = ids.index(doc_id)
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(ids):
        ids[idx], ids[swap] = ids[swap], ids[idx]
        for position, item_id in enumerate(ids, start=1):
            repo(ct.collection).update(item_id, {"order": position})
    return redirect(request.POST.get("next") or reverse("dashboard:list", args=[key]))


@staff_required
@require_POST
@rate_limit("upload", limit=240, window=60 * 10)
def upload_view(request, kind: str):
    """XHR endpoint used by the drag-and-drop uploader. One file per request."""
    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"ok": False, "error": "No file received."}, status=400)
    meta = {}
    if request.POST.get("date"):
        meta["date"] = request.POST["date"][:10]
    try:
        if kind == "photo":
            doc = media.store_photo(upload, meta)
            return JsonResponse({"ok": True, "id": doc["id"], "thumb": media.photo_urls(doc)["thumb"],
                                 "edit": reverse("dashboard:edit", args=["photos", doc["id"]])})
        if kind == "video":
            doc = media.store_video(upload, {**meta, "title": upload.name.rsplit(".", 1)[0][:120]})
            return JsonResponse({"ok": True, "id": doc["id"], "edit": reverse("dashboard:edit", args=["videos", doc["id"]])})
    except UploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    raise Http404


@staff_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    current = get_settings()
    if request.method == "POST":
        form = SettingsForm(request.POST)
        if form.is_valid():
            save_settings(form.to_settings())
            messages.success(request, "Settings saved.")
            return redirect("dashboard:settings")
    else:
        form = SettingsForm(initial=SettingsForm.initial_from(current))
    return render(request, "dashboard/settings.html", {"form": form})


@staff_required
@require_POST
def clear_demo_view(request):
    removed = 0
    for ct in CONTENT_TYPES.values():
        for doc in repo(ct.collection).find({"is_demo": True}, projection={"_id": 1}):
            if ct.key == "photos":
                media.delete_photo(doc["id"])
            elif ct.key == "videos":
                media.delete_video(doc["id"])
            else:
                repo(ct.collection).delete(doc["id"])
            removed += 1
    messages.success(request, f"Removed {removed} demo items.")
    return redirect("dashboard:home")


@staff_required
def export_view(request):
    fmt = request.GET.get("format")
    stamp = today().isoformat()
    if fmt == "json":
        response = HttpResponse(export.export_json_bytes(), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="our-love-{stamp}.json"'
        return response
    if fmt == "zip":
        handle = export.export_zip_file(include_media=request.GET.get("media") != "0")
        return FileResponse(handle, as_attachment=True, filename=f"our-love-{stamp}.zip", content_type="application/zip")
    counts = {ct.label_plural: repo(ct.collection).count() for ct in CONTENT_TYPES.values()}
    return render(request, "dashboard/export.html", {"counts": counts})
