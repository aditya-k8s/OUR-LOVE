"""Deterministic extraction of candidate memories from free text.

Nothing here invents information:
* dates come only from dates written in the text;
* titles are taken from the text itself (first sentence);
* locations are only suggested when a known place is named or a capitalised
  word follows "in/at/to" (flagged as a low-confidence suggestion);
* every candidate carries a confidence level and the reasons behind it.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTH_RX = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
ORD = r"(?:st|nd|rd|th)?"

DATE_PATTERNS = [
    ("iso", re.compile(r"\b((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})\b")),
    ("dmy_num", re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.]((?:19|20)\d{2})\b")),
    ("dmy_text", re.compile(rf"\b(\d{{1,2}}){ORD}\s+(?:of\s+)?{MONTH_RX}\.?,?\s+((?:19|20)\d{{2}})\b", re.I)),
    ("mdy_text", re.compile(rf"\b{MONTH_RX}\.?\s+(\d{{1,2}}){ORD},?\s+((?:19|20)\d{{2}})\b", re.I)),
]
PARTIAL_DATE = re.compile(rf"\b(?:(\d{{1,2}}){ORD}\s+(?:of\s+)?{MONTH_RX}|{MONTH_RX}\s+(\d{{1,2}}){ORD})\b", re.I)

CATEGORY_RULES: list[tuple[str, re.Pattern, bool]] = [
    # (category, pattern, strong signal)
    ("milestone", re.compile(r"\b(propos\w*|engaged|said yes|officially|started dating|became a couple|anniversary|moved in|married|wedding)\b", re.I), True),
    ("first", re.compile(r"\b(first time|for the first time|our first|my first|the first)\b", re.I), True),
    ("meeting", re.compile(r"\b(we met|first met|met (?:her|him|each other)|meet(?:ing)? (?:her|him|in person)|saw (?:her|him) for)\b", re.I), True),
    ("birthday", re.compile(r"\b(birthday|b'?day)\b", re.I), True),
    ("trip", re.compile(r"\b(trip|travel\w*|vacation|holiday|journey|flight|road trip|visited)\b", re.I), False),
    ("gift", re.compile(r"\b(gift\w*|gave (?:me|her|him)|present(?:ed)? (?:me|her|him)|surprised? (?:me|her|him))\b", re.I), False),
    ("date", re.compile(r"\b(went on a date|our date|dinner|movie|cafe|restaurant)\b", re.I), False),
    ("emotional", re.compile(r"\b(cried|tears|hurt|fight|argument|argued|apologi[sz]\w*|sorry|reconcil\w*|missed (?:her|him|you))\b", re.I), False),
    ("funny", re.compile(r"\b(laugh\w*|funny|joke\w*|silly)\b", re.I), False),
    ("future", re.compile(r"\b(want to|plan to|planning to|someday|one day|in the future|we will|we'll|dream of)\b", re.I), False),
    ("conversation", re.compile(r"\b(talked|conversation|chatted|called|phone call|video call|texted|messaged|told (?:me|her|him))\b", re.I), False),
]

FIRST_RULES = [
    ("first_message", re.compile(r"\bfirst (?:message|text)\b", re.I)),
    ("first_call", re.compile(r"\bfirst (?:phone |video )?call\b", re.I)),
    ("first_meeting", re.compile(r"\b(first (?:time we )?met|first meeting|met for the first time)\b", re.I)),
    ("first_photo", re.compile(r"\bfirst (?:photo|picture|selfie|pic)\b", re.I)),
    ("first_date", re.compile(r"\bfirst date\b", re.I)),
    ("first_gift", re.compile(r"\bfirst gift\b", re.I)),
    ("first_trip", re.compile(r"\bfirst trip\b", re.I)),
    ("first_kiss", re.compile(r"\bfirst kiss\b|\bkissed (?:for the first time)\b", re.I)),
    ("first_i_love_you", re.compile(r"\b(first [\"“]?i love you|said i love you for the first time)\b", re.I)),
]

HIGH_IMPORTANCE = re.compile(r"\b(propos\w*|engaged|married|i love you|first kiss|first met|officially)\b", re.I)
QUOTE_RX = re.compile(r"[“\"]([^“”\"\n]{8,300})[”\"]")
PLACE_RX = re.compile(r"\b(?:in|at|to|from|near)\s+((?:[A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,}){0,2})")
PLACE_STOP = {
    "The", "This", "That", "Our", "His", "Her", "She", "They", "Then", "There", "When", "What", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Night", "Morning", "Evening", "Home", "Love", "God",
} | {m for m in calendar.month_name if m} | {m for m in calendar.month_abbr if m}

MIN_WORDS = 6
MAX_DESCRIPTION = 5000


@dataclass
class Candidate:
    title: str
    description: str
    date: str | None
    category: str
    target: str
    importance: str
    confidence: str
    reasons: list[str]
    first_key: str = ""
    quote: str = ""
    location: dict = field(default_factory=lambda: {"name": "", "city": "", "country": ""})
    people: list[str] = field(default_factory=list)
    source_excerpt: str = ""
    written_on: str = ""
    origin: str = ""

    def as_suggestion(self) -> dict:
        return {
            "title": self.title,
            "date": self.date or "",
            "category": self.category,
            "description": self.description,
            "importance": self.importance,
            "first_key": self.first_key,
            "quote": self.quote,
            "location": self.location,
            "people": self.people,
            "tags": [],
        }


# ------------------------------------------------------------------ dates


def _month(name: str) -> int:
    return MONTHS[name.lower()[:3]]


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str) -> list[tuple[int, str, str]]:
    """Return (position, iso_date, matched_text) for every complete date in `text`."""
    found: list[tuple[int, str, str]] = []
    for kind, rx in DATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            if kind == "iso":
                d = _safe_date(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "dmy_num":
                # Day-first (UK/India convention); swap only when day-first is impossible.
                a, b = int(g[0]), int(g[1])
                d = _safe_date(int(g[2]), b, a) or _safe_date(int(g[2]), a, b)
            elif kind == "dmy_text":
                d = _safe_date(int(g[2]), _month(g[1]), int(g[0]))
            else:
                d = _safe_date(int(g[2]), _month(g[0]), int(g[1]))
            if d:
                found.append((m.start(), d.isoformat(), m.group(0)))
    found.sort()
    # drop overlapping matches (keep the earliest/longest)
    result: list[tuple[int, str, str]] = []
    last_end = -1
    for pos, iso, raw in found:
        if pos >= last_end:
            result.append((pos, iso, raw))
            last_end = pos + len(raw)
    return result


def _is_date_heading(line: str) -> str | None:
    stripped = line.strip().strip("#*_:-— ").strip()
    if not stripped or len(stripped) > 40:
        return None
    dates = find_dates(stripped)
    if dates and len(dates[0][2]) >= len(stripped) - 12:
        return dates[0][1]
    return None


# ------------------------------------------------------------------ segmentation


@dataclass
class Block:
    text: str
    heading_date: str | None
    written_on: str = ""
    origin: str = ""


def segment(text: str, written_on: str = "", origin: str = "") -> list[Block]:
    blocks: list[Block] = []
    current: list[str] = []
    heading: str | None = None

    def flush():
        body = "\n".join(current).strip()
        if body:
            blocks.append(Block(body, heading, written_on, origin))
        current.clear()

    for line in text.splitlines():
        heading_date = _is_date_heading(line)
        if heading_date:
            flush()
            heading = heading_date
            continue
        if not line.strip():
            flush()
            continue
        current.append(line.rstrip())
    flush()
    return blocks


# ------------------------------------------------------------------ extraction


def _first_sentence(text: str, limit: int = 80) -> str:
    sentence = re.split(r"(?<=[.!?])\s+|\n", text.strip(), maxsplit=1)[0].strip()
    sentence = sentence.strip(" -—:*#\"“”")
    if len(sentence) <= limit:
        return sentence
    cut = sentence[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _strip_leading_date(text: str) -> str:
    dates = find_dates(text[:60])
    if dates and dates[0][0] <= 3:
        _, _, raw = dates[0]
        text = text[dates[0][0] + len(raw):]
    return text.lstrip(" ,:-—\n")


def _location(text: str, known_places: dict[str, dict]) -> tuple[dict, str | None]:
    lower = text.lower()
    for name, loc in known_places.items():
        if name and re.search(rf"\b{re.escape(name.lower())}\b", lower):
            return loc, f"Mentions known place “{name}”"
    for m in PLACE_RX.finditer(text):
        words = m.group(1).split()
        while words and words[0] in PLACE_STOP:
            words.pop(0)
        while words and words[-1] in PLACE_STOP:
            words.pop()
        if words:
            name = " ".join(words)
            return {"name": "", "city": name, "country": ""}, f"Possible place “{name}” (please check)"
    return {"name": "", "city": "", "country": ""}, None


def extract_block(block: Block, known_places: dict[str, dict], names: list[str]) -> list[Candidate]:
    raw = block.text.strip()
    words = len(raw.split())
    reasons: list[str] = []
    score = 0

    inline = find_dates(raw)
    event_date = None
    if inline:
        event_date = inline[0][1]
        reasons.append(f"Date written in the text ({inline[0][2]})")
        score += 2
    elif block.heading_date:
        event_date = block.heading_date
        reasons.append("Date taken from the heading above this passage")
        score += 1
    else:
        partial = PARTIAL_DATE.search(raw)
        reasons.append(
            f"Mentions “{partial.group(0)}” but no year, so no date was set" if partial else "No date found"
        )

    categories = []
    strong = False
    for cat, rx, is_strong in CATEGORY_RULES:
        if rx.search(raw):
            categories.append(cat)
            strong = strong or is_strong
    first_key = next((key for key, rx in FIRST_RULES if rx.search(raw)), "")
    if first_key:
        categories.insert(0, "first")
        reasons.append("Describes one of your firsts")
        score += 1
    if strong:
        score += 1
    if categories:
        reasons.append("Keywords suggest: " + ", ".join(dict.fromkeys(categories)))

    if not categories and not event_date:
        return []
    if words < MIN_WORDS and not event_date:
        return []

    category = categories[0] if categories else "memory"
    if category == "future" and event_date is None:
        target = "future"
    elif category in ("milestone", "first", "meeting", "birthday", "trip") and event_date:
        target = "timeline"
    else:
        target = "memories"

    location, loc_reason = _location(raw, known_places)
    if loc_reason:
        reasons.append(loc_reason)
    people = [n for n in names if n and re.search(rf"\b{re.escape(n)}\b", raw, re.I)]

    importance = "high" if (HIGH_IMPORTANCE.search(raw) or first_key) else ("medium" if strong or event_date else "low")
    confidence = "high" if score >= 3 else "medium" if score == 2 else "low"
    if not event_date:
        confidence = "low"  # without a written date the placement in the story is uncertain

    body = _strip_leading_date(raw)
    title = _first_sentence(body) or "Untitled memory"
    quotes = [q.strip() for q in QUOTE_RX.findall(raw)]

    main = Candidate(
        title=title,
        description=body[:MAX_DESCRIPTION],
        date=event_date,
        category=category,
        target=target,
        importance=importance,
        confidence=confidence,
        reasons=reasons,
        first_key=first_key,
        quote=quotes[0] if quotes else "",
        location=location,
        people=people,
        source_excerpt=raw[:1500],
        written_on=block.written_on,
        origin=block.origin,
    )
    out = [main]
    for q in quotes[:3]:
        out.append(
            Candidate(
                title=_first_sentence(q, 60),
                description=title,
                date=event_date,
                category="other",
                target="messages",
                importance="medium",
                confidence="medium" if event_date else "low",
                reasons=["Words in quotation marks", *(r for r in reasons[:1])],
                quote=q,
                source_excerpt=raw[:1500],
                written_on=block.written_on,
                origin=block.origin,
            )
        )
    return out


def extract(texts, known_places: dict[str, dict] | None = None, names: list[str] | None = None) -> tuple[list[Candidate], int]:
    """Return (candidates, number_of_blocks_examined)."""
    candidates: list[Candidate] = []
    seen: set[str] = set()
    examined = 0
    for source in texts:
        for block in segment(source.text, source.written_on, source.origin):
            examined += 1
            for cand in extract_block(block, known_places or {}, names or []):
                fingerprint = f"{cand.target}|{cand.date}|{' '.join(cand.description.lower().split())[:300]}"
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                candidates.append(cand)
    return candidates, examined
