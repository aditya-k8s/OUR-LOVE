"""REST API driven by the content registry.

GET    /api/<type>/          paginated list (visibility rules applied)
POST   /api/<type>/          create (staff only)
GET    /api/<type>/<id>/     detail
PATCH  /api/<type>/<id>/     partial update (staff only)
PUT    /api/<type>/<id>/     full update (staff only)
DELETE /api/<type>/<id>/     delete (staff only)
GET    /api/search/?q=       global search
GET    /api/stats/           relationship statistics
"""
from __future__ import annotations

from datetime import date, datetime

from django.http import Http404
from django.utils.datastructures import MultiValueDict
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content import services as content
from apps.core.registry import CONTENT_TYPES
from apps.core.repository import repo
from apps.dashboard.forms import build_form, to_document, to_initial
from apps.media import services as media

# URL slugs used by the API (matching the specification) -> registry keys.
API_TYPES = {
    "timeline": "timeline",
    "memories": "memories",
    "photos": "photos",
    "videos": "videos",
    "letters": "letters",
    "messages": "messages",
    "places": "places",
    "gifts": "gifts",
    "dates": "dates",
    "future-plans": "future",
}
PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
INTERNAL_FIELDS = {"source"}


def _ct(slug: str):
    key = API_TYPES.get(slug)
    if not key:
        raise Http404
    return CONTENT_TYPES[key]


def _json_ready(doc: dict) -> dict:
    out = {}
    for k, v in doc.items():
        if k in INTERNAL_FIELDS:
            continue
        out[k] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


def _present(ct, doc: dict) -> dict:
    doc = _json_ready(doc)
    if ct.key == "photos":
        doc["urls"] = media.photo_urls(doc)
        for key in ("storage_key", "thumb_key", "medium_key"):
            doc.pop(key, None)
    if ct.key == "videos":
        doc["src"] = media.video_src(doc)
        doc.pop("storage_key", None)
    return doc


def _validate(ct, payload: dict, existing: dict | None = None):
    """Validate using the same form as the admin UI so rules never diverge."""
    base = to_initial(ct, existing) if existing else {}
    data = {}
    for key, value in base.items():
        if value is None:
            continue
        data[key] = value.isoformat() if isinstance(value, date) else value
    for key, value in payload.items():
        if isinstance(value, dict) and key == "location":
            for part, part_value in value.items():
                data[f"location__{part}"] = part_value
        elif isinstance(value, list) and key in ct.field_map and ct.field_map[key].kind == "tags":
            data[key] = ", ".join(str(v) for v in value)
        else:
            data[key] = value
    multi = MultiValueDict()
    for key, value in data.items():
        if isinstance(value, bool):
            if value:
                multi[key] = "on"
        elif isinstance(value, list):
            multi.setlist(key, [str(v) for v in value])
        else:
            multi[key] = "" if value is None else str(value)
    form = build_form(ct, data=multi)
    if not form.is_valid():
        return None, form.errors.get_json_data()
    return to_document(ct, form.cleaned_data), None


class CollectionView(APIView):
    def get(self, request, slug: str):
        ct = _ct(slug)
        try:
            size = min(max(int(request.query_params.get("page_size", PAGE_SIZE)), 1), MAX_PAGE_SIZE)
            page = max(int(request.query_params.get("page", 1)), 1)
        except ValueError:
            return Response({"detail": "Invalid pagination parameters."}, status=400)
        filters = content.clean_filters(request.query_params)
        query = content.visible(request, ct.key, content.build_filter_query(filters))
        total = repo(ct.collection).count(query)
        items = repo(ct.collection).find(query, sort=ct.default_sort, limit=size, skip=(page - 1) * size)
        return Response({
            "count": total,
            "page": page,
            "page_size": size,
            "next": page * size < total,
            "results": [_present(ct, d) for d in items],
        })

    def post(self, request, slug: str):
        ct = _ct(slug)
        if not ct.creatable:
            return Response({"detail": "Upload photos through the dashboard uploader."}, status=405)
        doc, errors = _validate(ct, request.data)
        if errors:
            return Response({"errors": errors}, status=400)
        new_id = repo(ct.collection).insert(doc)
        return Response(_present(ct, repo(ct.collection).get(new_id)), status=status.HTTP_201_CREATED)


class DocumentView(APIView):
    def _get(self, request, ct, doc_id):
        doc = repo(ct.collection).get(doc_id, content.visible(request, ct.key))
        if not doc:
            raise Http404
        return doc

    def get(self, request, slug: str, doc_id: str):
        ct = _ct(slug)
        return Response(_present(ct, self._get(request, ct, doc_id)))

    def _update(self, request, slug: str, doc_id: str, partial: bool):
        ct = _ct(slug)
        existing = repo(ct.collection).get(doc_id)
        if not existing:
            raise Http404
        doc, errors = _validate(ct, request.data, existing if partial else None)
        if errors:
            return Response({"errors": errors}, status=400)
        repo(ct.collection).update(doc_id, doc)
        return Response(_present(ct, repo(ct.collection).get(doc_id)))

    def patch(self, request, slug: str, doc_id: str):
        return self._update(request, slug, doc_id, partial=True)

    def put(self, request, slug: str, doc_id: str):
        return self._update(request, slug, doc_id, partial=False)

    def delete(self, request, slug: str, doc_id: str):
        ct = _ct(slug)
        if ct.key == "photos":
            ok = media.delete_photo(doc_id)
        elif ct.key == "videos":
            ok = media.delete_video(doc_id)
        else:
            ok = repo(ct.collection).delete(doc_id)
        if not ok:
            raise Http404
        return Response(status=status.HTTP_204_NO_CONTENT)


class SearchView(APIView):
    def get(self, request):
        q = request.query_params.get("q", "")
        groups = content.search(request, q)
        return Response({
            "query": q.strip()[:100],
            "results": {
                g.content_type.key: [
                    {"id": d["id"], "title": d.get(g.content_type.title_field) or "", "date": d.get(g.content_type.date_field or "date", "")}
                    for d in g.results
                ]
                for g in groups
            },
        })


class StatsView(APIView):
    def get(self, request):
        duration = content.relationship_duration()
        return Response({
            "together": {"years": duration.years, "months": duration.months, "days": duration.days,
                          "total_days": duration.total_days} if duration else None,
            "stats": content.stats(request),
        })
