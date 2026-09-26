"""Find existing memories that an imported candidate may duplicate."""
from __future__ import annotations

import re
from datetime import timedelta
from difflib import SequenceMatcher

from apps.core.dates import parse_iso
from apps.core.repository import repo

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "we", "our", "us", "i", "my", "me",
    "she", "he", "her", "him", "it", "was", "were", "is", "are", "that", "this", "day", "time", "when", "so", "very",
}
# Very small normalisation so "met", "meeting" and "meet" compare equal.
STEMS = {"met": "meet", "meeting": "meet", "meets": "meet", "proposed": "propose", "proposal": "propose",
         "kissed": "kiss", "called": "call", "talked": "talk", "birthday": "birthday", "bday": "birthday"}

THRESHOLD = 0.55
SOURCES = ("timeline_events", "memories")


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    out = set()
    for w in words:
        w = STEMS.get(w, w)
        if w not in STOPWORDS and len(w) > 1:
            out.add(w)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(cand: dict, doc: dict) -> float:
    title_score = max(
        jaccard(tokens(cand.get("title")), tokens(doc.get("title"))),
        SequenceMatcher(None, (cand.get("title") or "").lower(), (doc.get("title") or "").lower()).ratio() * 0.8,
    )
    desc_a, desc_b = tokens(cand.get("description")), tokens(doc.get("description"))
    desc_score = jaccard(desc_a, desc_b)
    score = 0.65 * title_score + 0.35 * desc_score

    d1, d2 = parse_iso(cand.get("date")), parse_iso(doc.get("date"))
    if d1 and d2:
        gap = abs((d1 - d2).days)
        score += 0.3 if gap == 0 else 0.12 if gap <= 3 else -0.25 if gap > 30 else 0
    return round(min(score, 1.0), 3)


def find_duplicates(cand: dict, limit: int = 3) -> list[dict]:
    d = parse_iso(cand.get("date"))
    matches: list[dict] = []
    for collection in SOURCES:
        query: dict = {}
        if d:
            window = [(d - timedelta(days=3)).isoformat(), (d + timedelta(days=3)).isoformat()]
            title_words = [w for w in tokens(cand.get("title")) if len(w) > 3][:5]
            ors: list[dict] = [{"date": {"$gte": window[0], "$lte": window[1]}}]
            ors += [{"title": {"$regex": re.escape(w), "$options": "i"}} for w in title_words]
            query = {"$or": ors}
        else:
            title_words = [w for w in tokens(cand.get("title")) if len(w) > 3][:5]
            if not title_words:
                continue
            query = {"$or": [{"title": {"$regex": re.escape(w), "$options": "i"}} for w in title_words]}
        for doc in repo(collection).find(query, limit=200, projection={"title": 1, "date": 1, "description": 1}):
            score = similarity(cand, doc)
            if score >= THRESHOLD:
                matches.append({"collection": collection, "id": doc["id"], "title": doc.get("title", ""),
                                "date": doc.get("date", ""), "score": score})
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:limit]
