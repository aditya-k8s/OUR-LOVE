"""Import workflow: upload -> parse -> extract -> pending review -> approve/merge/reject."""
from __future__ import annotations

from apps.core.registry import CONTENT_TYPES
from apps.core.repository import now_utc, repo
from apps.core.site_settings import get_settings

from .duplicates import find_duplicates
from .extractor import extract
from .parsers import ParseError, parse_upload

# Review targets and the registry key each maps to.
TARGETS = {
    "timeline": "Timeline event",
    "memories": "Memory",
    "messages": "Words I'll never forget",
    "gifts": "Gift",
    "places": "Place",
    "dates": "Important date",
    "future": "Future plan",
}


def _known_places() -> dict[str, dict]:
    places: dict[str, dict] = {}
    for p in repo("places").find({}, projection={"name": 1, "city": 1, "country": 1}):
        loc = {"name": p.get("name", ""), "city": p.get("city", ""), "country": p.get("country", "")}
        for key in (p.get("name"), p.get("city")):
            if key and len(key) > 2:
                places.setdefault(key, loc)
    for col in ("memories", "timeline_events"):
        for city in repo(col).distinct("location.city"):
            if isinstance(city, str) and len(city) > 2:
                places.setdefault(city, {"name": "", "city": city, "country": ""})
    return places


def run_import(filename: str, raw: bytes, user=None) -> dict:
    """Parse a file and store every candidate as a pending memory. Returns the job document."""
    job_id = repo("import_jobs").insert(
        {"filename": filename[:200], "status": "processing", "stats": {}, "error": "",
         "created_by": getattr(user, "username", "")}
    )
    try:
        file_type, texts = parse_upload(filename, raw)
    except ParseError as exc:
        repo("import_jobs").update(job_id, {"status": "failed", "error": str(exc)})
        return repo("import_jobs").get(job_id)

    rel = get_settings()["relationship"]
    names = [n for n in (rel.get("person_one"), rel.get("person_two")) if n]
    candidates, examined = extract(texts, _known_places(), names)

    counts = {"low": 0, "medium": 0, "high": 0}
    duplicates = 0
    docs = []
    for cand in candidates:
        suggestion = cand.as_suggestion()
        dups = find_duplicates(suggestion) if cand.target in ("timeline", "memories") else []
        duplicates += bool(dups)
        counts[cand.confidence] += 1
        stamp = now_utc()
        docs.append({
            "job_id": job_id,
            "status": "pending",
            "target": cand.target,
            "suggested": suggestion,
            "confidence": cand.confidence,
            "reasons": cand.reasons,
            "source_excerpt": cand.source_excerpt,
            "written_on": cand.written_on,
            "origin": cand.origin,
            "possible_duplicates": dups,
            "created_at": stamp,
            "updated_at": stamp,
        })
    if docs:
        repo("pending_memories").col.insert_many(docs)
    repo("import_jobs").update(job_id, {
        "status": "ready",
        "file_type": file_type,
        "stats": {"sources": len(texts), "passages": examined, "candidates": len(candidates),
                  "duplicates": duplicates, **counts},
    })
    return repo("import_jobs").get(job_id)


def build_document(target: str, s: dict) -> tuple[dict, list[str]]:
    """Map a reviewed suggestion onto the target collection's fields. Returns (doc, errors)."""
    errors: list[str] = []
    loc = s.get("location") or {"name": "", "city": "", "country": ""}
    base = {"is_published": True, "is_public": False}
    if target == "timeline":
        if not s.get("date"):
            errors.append("Timeline events need a date.")
        doc = {k: s.get(k, "") for k in ("title", "date", "category", "description", "quote", "importance", "first_key")}
        doc.update(location=loc, people=s.get("people", []), tags=s.get("tags", []), photo_ids=[], video_ids=[],
                   place_id="", end_date="", is_favorite=False)
        doc["category"] = doc["category"] or "memory"
    elif target == "memories":
        doc = {k: s.get(k, "") for k in ("title", "date", "category", "description", "importance")}
        doc.update(location=loc, people=s.get("people", []), tags=s.get("tags", []), photo_ids=[], video_ids=[],
                   place_id="", mood="", is_favorite=False)
    elif target == "messages":
        text = s.get("quote") or s.get("description") or ""
        if not text:
            errors.append("A message needs the words themselves (use the Quote field).")
        doc = {"message": text, "date": s.get("date", ""), "sender": s.get("sender", ""),
               "context": s.get("description", "") if s.get("quote") else "", "category": "other"}
    elif target == "gifts":
        doc = {"gift": s.get("title", ""), "date": s.get("date", ""), "given_by": "", "given_to": "",
               "occasion": "", "description": s.get("description", ""), "photo_id": "", "memory_id": ""}
    elif target == "places":
        doc = {"name": loc.get("name") or loc.get("city") or s.get("title", ""), "city": loc.get("city", ""),
               "country": loc.get("country", ""), "date": s.get("date", ""), "description": s.get("description", ""),
               "latitude": None, "longitude": None, "photo_ids": [], "memory_ids": []}
    elif target == "dates":
        if not s.get("date"):
            errors.append("Important dates need a date.")
        doc = {"title": s.get("title", ""), "date": s.get("date", ""), "kind": "other", "recurring_yearly": False,
               "description": s.get("description", "")}
    elif target == "future":
        doc = {"title": s.get("title", ""), "description": s.get("description", ""), "target_date": s.get("date", ""),
               "completed": False, "completion_date": "", "completion_photo_id": ""}
    else:
        return {}, ["Unknown destination."]
    title_field = CONTENT_TYPES[target].title_field
    if not doc.get(title_field):
        errors.append("A title is required.")
    return {**doc, **base}, errors


def approve(pending: dict, suggestion: dict, target: str) -> tuple[str | None, list[str]]:
    doc, errors = build_document(target, suggestion)
    if errors:
        return None, errors
    ct = CONTENT_TYPES[target]
    if ct.orderable:
        last = repo(ct.collection).find({}, sort=(("order", -1),), limit=1)
        doc["order"] = int((last[0].get("order") or 0) + 1) if last else 1
    doc["source"] = {"type": "import", "job_id": pending.get("job_id"), "pending_id": pending["id"]}
    new_id = repo(ct.collection).insert(doc)
    repo("pending_memories").update(pending["id"], {
        "status": "approved", "suggested": suggestion, "target": target,
        "resolved_ref": {"collection": ct.collection, "id": new_id},
    })
    return new_id, []


def merge(pending: dict, suggestion: dict, collection: str, target_id: str) -> bool:
    """Fold the candidate into an existing memory without overwriting what is already there."""
    if collection not in ("timeline_events", "memories"):
        return False
    existing = repo(collection).get(target_id)
    if not existing:
        return False
    change: dict = {}
    new_text = (suggestion.get("description") or "").strip()
    old_text = (existing.get("description") or "").strip()
    if new_text and new_text not in old_text:
        change["description"] = f"{old_text}\n\n{new_text}".strip()
    for key in ("date", "quote", "importance", "category"):
        if suggestion.get(key) and not existing.get(key) and (key != "quote" or collection == "timeline_events"):
            change[key] = suggestion[key]
    loc = suggestion.get("location") or {}
    old_loc = existing.get("location") or {}
    if any(loc.values()) and not any(old_loc.values()):
        change["location"] = loc
    for key in ("tags", "people"):
        merged = list(dict.fromkeys((existing.get(key) or []) + (suggestion.get(key) or [])))
        if merged != (existing.get(key) or []):
            change[key] = merged
    if change:
        repo(collection).update(target_id, change)
    repo("pending_memories").update(pending["id"], {
        "status": "merged", "suggested": suggestion, "resolved_ref": {"collection": collection, "id": target_id},
    })
    return True


def reject(pending_id: str) -> bool:
    return repo("pending_memories").update(pending_id, {"status": "rejected"})
