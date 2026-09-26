"""Content-type registry.

Each collection that the admin can manage is described once here. Admin forms,
validation, list columns, the API, search and export are all driven by these
descriptions (see docs/ARCHITECTURE.md, D3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ------------------------------------------------------------------ vocabularies

TIMELINE_CATEGORIES = (
    ("first", "First"),
    ("meeting", "Meeting"),
    ("date", "Date"),
    ("birthday", "Birthday"),
    ("trip", "Trip"),
    ("gift", "Gift"),
    ("memory", "Memory"),
    ("conversation", "Conversation"),
    ("milestone", "Milestone"),
    ("emotional", "Emotional"),
    ("funny", "Funny"),
    ("future", "Future"),
    ("other", "Other"),
)

IMPORTANCE = (("low", "Low"), ("medium", "Medium"), ("high", "High"))

FIRST_KEYS = (
    ("first_message", "First message"),
    ("first_call", "First call"),
    ("first_meeting", "First meeting"),
    ("first_photo", "First photo"),
    ("first_date", "First date"),
    ("first_gift", "First gift"),
    ("first_trip", "First trip"),
    ("first_kiss", "First kiss"),
    ("first_i_love_you", "First “I love you”"),
    ("first_special_memory", "First special memory"),
)

MOODS = (
    ("joyful", "Joyful"),
    ("tender", "Tender"),
    ("calm", "Calm"),
    ("playful", "Playful"),
    ("bittersweet", "Bittersweet"),
    ("emotional", "Emotional"),
    ("adventurous", "Adventurous"),
    ("other", "Other"),
)

MESSAGE_CATEGORIES = (
    ("love", "Love"),
    ("promise", "Promise"),
    ("comfort", "Comfort"),
    ("encouragement", "Encouragement"),
    ("apology", "Apology"),
    ("funny", "Funny"),
    ("other", "Other"),
)

DATE_KINDS = (
    ("birthday", "Birthday"),
    ("anniversary", "Anniversary"),
    ("first_meeting", "First meeting"),
    ("milestone", "Milestone"),
    ("trip", "Trip"),
    ("future_plan", "Future plan"),
    ("other", "Other"),
)


# ------------------------------------------------------------------ descriptors


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    # kinds: text, textarea, longtext, date, select, tags, bool, int, float,
    #        url, location, photos, photo, videos, place, memory
    required: bool = False
    choices: tuple = ()
    help: str = ""
    max_length: int = 300
    searchable: bool = False
    in_list: bool = False
    placeholder: str = ""
    wide: bool = False


@dataclass(frozen=True)
class ContentType:
    key: str
    collection: str
    label: str
    label_plural: str
    title_field: str
    fields: tuple[Field, ...]
    date_field: str | None = "date"
    publishable: bool = True
    orderable: bool = False
    creatable: bool = True
    public_url: str | None = None
    intro: str = ""
    default_sort: tuple = (("date", -1), ("created_at", -1))
    extra_search: tuple = field(default_factory=tuple)

    @property
    def field_map(self) -> dict[str, Field]:
        return {f.name: f for f in self.fields}

    @property
    def searchable_fields(self) -> list[str]:
        names = [f.name for f in self.fields if f.searchable]
        return names + list(self.extra_search)

    @property
    def list_fields(self) -> list[Field]:
        return [f for f in self.fields if f.in_list]


LOCATION_SEARCH = ("location.name", "location.city", "location.country")

CONTENT_TYPES: dict[str, ContentType] = {}


def register(ct: ContentType) -> ContentType:
    CONTENT_TYPES[ct.key] = ct
    return ct


register(
    ContentType(
        key="timeline",
        collection="timeline_events",
        label="Timeline event",
        label_plural="Timeline",
        title_field="title",
        orderable=True,
        public_url="content:story",
        intro="The moments that shaped your story, in order.",
        default_sort=(("date", 1), ("order", 1), ("created_at", 1)),
        extra_search=LOCATION_SEARCH,
        fields=(
            Field("title", "Title", required=True, searchable=True, in_list=True, placeholder="Our first meeting"),
            Field("date", "Date", "date", required=True, in_list=True),
            Field("end_date", "End date", "date", help="Optional, for trips or periods."),
            Field("category", "Category", "select", required=True, choices=TIMELINE_CATEGORIES, in_list=True),
            Field("first_key", "Marks our first…", "select", choices=(("", "Not a first"),) + FIRST_KEYS,
                  help="Shows this moment in the “Our Firsts” section."),
            Field("description", "Description", "longtext", searchable=True, max_length=20000, wide=True),
            Field("quote", "Quote", "textarea", searchable=True, max_length=1000, wide=True,
                  help="Only words that were actually said or written."),
            Field("location", "Location", "location", wide=True),
            Field("place_id", "Linked place", "place"),
            Field("photo_ids", "Photos", "photos", wide=True),
            Field("video_ids", "Videos", "videos", wide=True),
            Field("people", "People", "tags", searchable=True),
            Field("tags", "Tags", "tags", searchable=True),
            Field("importance", "Importance", "select", choices=IMPORTANCE, in_list=True),
            Field("is_favorite", "Favourite", "bool"),
        ),
    )
)

register(
    ContentType(
        key="memories",
        collection="memories",
        label="Memory",
        label_plural="Memories",
        title_field="title",
        public_url="content:memories",
        intro="Moments worth keeping, with photos, places and feelings.",
        extra_search=LOCATION_SEARCH,
        fields=(
            Field("title", "Title", required=True, searchable=True, in_list=True, placeholder="The day we met"),
            Field("date", "Date", "date", in_list=True),
            Field("category", "Category", "select", choices=TIMELINE_CATEGORIES, in_list=True),
            Field("description", "Description", "longtext", searchable=True, max_length=20000, wide=True),
            Field("location", "Location", "location", wide=True),
            Field("place_id", "Linked place", "place"),
            Field("photo_ids", "Photos", "photos", wide=True),
            Field("video_ids", "Videos", "videos", wide=True),
            Field("people", "People", "tags", searchable=True),
            Field("tags", "Tags", "tags", searchable=True),
            Field("mood", "Mood", "select", choices=(("", "—"),) + MOODS),
            Field("importance", "Importance", "select", choices=IMPORTANCE, in_list=True),
            Field("is_favorite", "Favourite", "bool"),
        ),
    )
)

register(
    ContentType(
        key="photos",
        collection="photos",
        label="Photo",
        label_plural="Photos",
        title_field="caption",
        creatable=False,
        public_url="content:gallery",
        intro="Upload photos with drag and drop, then add captions.",
        extra_search=LOCATION_SEARCH,
        fields=(
            Field("caption", "Caption", searchable=True, in_list=True, max_length=500),
            Field("date", "Date", "date", in_list=True),
            Field("location", "Location", "location", wide=True),
            Field("tags", "Tags", "tags", searchable=True),
        ),
    )
)

register(
    ContentType(
        key="videos",
        collection="videos",
        label="Video",
        label_plural="Videos",
        title_field="title",
        public_url="content:moments",
        intro="Upload MP4 or WebM files, or link a secure video URL.",
        extra_search=LOCATION_SEARCH,
        fields=(
            Field("title", "Title", required=True, searchable=True, in_list=True),
            Field("date", "Date", "date", in_list=True),
            Field("external_url", "Video URL", "url",
                  help="HTTPS link to an MP4/WebM file. Leave empty when uploading a file."),
            Field("caption", "Caption", "textarea", searchable=True, max_length=1000, wide=True),
            Field("poster_photo_id", "Poster image", "photo"),
            Field("location", "Location", "location", wide=True),
            Field("tags", "Tags", "tags", searchable=True),
        ),
    )
)

register(
    ContentType(
        key="letters",
        collection="letters",
        label="Letter",
        label_plural="Letters",
        title_field="title",
        public_url="content:letters",
        intro="Words written slowly, meant to be read again.",
        fields=(
            Field("title", "Title", required=True, searchable=True, in_list=True, placeholder="A letter to you"),
            Field("date", "Date", "date", in_list=True),
            Field("recipient", "To", searchable=True, in_list=True),
            Field("author", "From", searchable=True),
            Field("content", "Letter", "longtext", required=True, searchable=True, max_length=50000, wide=True),
            Field("photo_id", "Photo", "photo"),
        ),
    )
)

register(
    ContentType(
        key="messages",
        collection="messages",
        label="Message",
        label_plural="Words I'll Never Forget",
        title_field="message",
        public_url="content:words",
        intro="Words that stayed long after the conversation ended.",
        fields=(
            Field("message", "Message", "textarea", required=True, searchable=True, in_list=True, max_length=3000, wide=True),
            Field("date", "Date", "date", in_list=True),
            Field("sender", "Said by", searchable=True, in_list=True),
            Field("context", "Context", "textarea", searchable=True, max_length=2000, wide=True),
            Field("category", "Category", "select", choices=MESSAGE_CATEGORIES),
        ),
    )
)

register(
    ContentType(
        key="places",
        collection="places",
        label="Place",
        label_plural="Places",
        title_field="name",
        public_url="content:places",
        intro="Places that became memories. Coordinates stay private unless the place is public.",
        fields=(
            Field("name", "Place name", required=True, searchable=True, in_list=True),
            Field("city", "City", searchable=True, in_list=True),
            Field("country", "Country", searchable=True),
            Field("date", "Date", "date", in_list=True),
            Field("description", "Description", "longtext", searchable=True, max_length=10000, wide=True),
            Field("latitude", "Latitude", "float"),
            Field("longitude", "Longitude", "float"),
            Field("photo_ids", "Photos", "photos", wide=True),
            Field("memory_ids", "Linked memories", "memory", wide=True),
        ),
    )
)

register(
    ContentType(
        key="gifts",
        collection="gifts",
        label="Gift",
        label_plural="Little Things",
        title_field="gift",
        public_url="content:gifts",
        intro="The little things, and the thought behind them.",
        fields=(
            Field("gift", "Gift", required=True, searchable=True, in_list=True),
            Field("date", "Date", "date", in_list=True),
            Field("given_by", "Given by", searchable=True, in_list=True),
            Field("given_to", "Given to", searchable=True),
            Field("occasion", "Occasion", searchable=True),
            Field("description", "Description", "longtext", searchable=True, max_length=5000, wide=True),
            Field("photo_id", "Photo", "photo"),
            Field("memory_id", "Linked memory", "memory"),
        ),
    )
)

register(
    ContentType(
        key="dates",
        collection="important_dates",
        label="Important date",
        label_plural="Important Dates",
        title_field="title",
        public_url="content:calendar",
        intro="Birthdays, anniversaries and the days you never want to forget.",
        fields=(
            Field("title", "Title", required=True, searchable=True, in_list=True),
            Field("date", "Date", "date", required=True, in_list=True),
            Field("kind", "Kind", "select", choices=DATE_KINDS, in_list=True),
            Field("recurring_yearly", "Repeats every year", "bool"),
            Field("description", "Description", "textarea", searchable=True, max_length=3000, wide=True),
        ),
    )
)

register(
    ContentType(
        key="future",
        collection="future_plans",
        label="Future plan",
        label_plural="Things We Still Want To Do",
        title_field="title",
        orderable=True,
        date_field="target_date",
        public_url="content:future",
        intro="Plans, hopes and adventures still to come.",
        default_sort=(("completed", 1), ("order", 1), ("created_at", 1)),
        fields=(
            Field("title", "Title", required=True, searchable=True, in_list=True, placeholder="Watch the sunrise together"),
            Field("description", "Description", "textarea", searchable=True, max_length=3000, wide=True),
            Field("target_date", "Target date", "date", in_list=True),
            Field("completed", "Completed", "bool", in_list=True),
            Field("completion_date", "Completed on", "date"),
            Field("completion_photo_id", "Photo after completion", "photo"),
        ),
    )
)


def get_content_type(key: str) -> ContentType | None:
    return CONTENT_TYPES.get(key)


def by_collection(collection: str) -> ContentType | None:
    return next((ct for ct in CONTENT_TYPES.values() if ct.collection == collection), None)


def choice_label(choices: tuple, value) -> str:
    return dict(choices).get(value, value or "")
