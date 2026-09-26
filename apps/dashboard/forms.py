"""Admin forms generated from the content-type registry."""
from __future__ import annotations

from django import forms

from apps.core.dates import parse_iso
from apps.core.registry import ContentType, Field
from apps.core.repository import repo

LOCATION_PARTS = ("name", "city", "country")


def _photo_choices() -> list[tuple[str, str]]:
    return [
        (p["id"], p.get("caption") or p.get("original_name") or "Photo")
        for p in repo("photos").find({}, sort=(("created_at", -1),), limit=500,
                                      projection={"caption": 1, "original_name": 1})
    ]


def _choices(collection: str, label_field: str, limit: int = 500) -> list[tuple[str, str]]:
    return [
        (d["id"], d.get(label_field) or "Untitled")
        for d in repo(collection).find({}, sort=(("date", -1), ("created_at", -1)), limit=limit,
                                       projection={label_field: 1, "date": 1})
    ]


class DateInput(forms.DateInput):
    input_type = "date"


def build_field(spec: Field) -> dict[str, forms.Field]:
    """Return the form field(s) for one registry field (location expands to three)."""
    common = {"label": spec.label, "required": spec.required, "help_text": spec.help}
    attrs = {"placeholder": spec.placeholder} if spec.placeholder else {}
    kind = spec.kind
    if kind == "text":
        return {spec.name: forms.CharField(max_length=spec.max_length, widget=forms.TextInput(attrs=attrs), **common)}
    if kind in ("textarea", "longtext"):
        rows = 12 if kind == "longtext" else 3
        return {spec.name: forms.CharField(max_length=spec.max_length, widget=forms.Textarea(attrs={"rows": rows, **attrs}), strip=False if kind == "longtext" else True, **common)}
    if kind == "date":
        return {spec.name: forms.DateField(widget=DateInput(format="%Y-%m-%d"), input_formats=["%Y-%m-%d", "%d/%m/%Y"], **common)}
    if kind == "select":
        choices = list(spec.choices)
        if not spec.required and not any(c[0] == "" for c in choices):
            choices = [("", "—")] + choices
        return {spec.name: forms.ChoiceField(choices=choices, **common)}
    if kind == "tags":
        return {spec.name: forms.CharField(max_length=1000, widget=forms.TextInput(attrs={"placeholder": "Comma separated"}), **{**common, "help_text": spec.help or "Separate with commas."})}
    if kind == "bool":
        return {spec.name: forms.BooleanField(**{**common, "required": False})}
    if kind == "int":
        return {spec.name: forms.IntegerField(**common)}
    if kind == "float":
        bounds = {"latitude": (-90, 90), "longitude": (-180, 180)}.get(spec.name, (None, None))
        return {spec.name: forms.FloatField(min_value=bounds[0], max_value=bounds[1], **common)}
    if kind == "url":
        return {spec.name: forms.URLField(max_length=1000, assume_scheme="https", **common)}
    if kind == "location":
        return {
            f"{spec.name}__{part}": forms.CharField(label=f"{spec.label} {part}".capitalize() if part != "name" else spec.label,
                                                     max_length=200, required=False,
                                                     widget=forms.TextInput(attrs={"placeholder": {"name": "Place", "city": "City", "country": "Country"}[part]}))
            for part in LOCATION_PARTS
        }
    if kind == "photos":
        return {spec.name: forms.MultipleChoiceField(choices=_photo_choices(), widget=forms.CheckboxSelectMultiple, **{**common, "required": False})}
    if kind == "photo":
        return {spec.name: forms.ChoiceField(choices=[("", "No photo")] + _photo_choices(), **{**common, "required": False})}
    if kind == "videos":
        return {spec.name: forms.MultipleChoiceField(choices=_choices("videos", "title"), widget=forms.CheckboxSelectMultiple, **{**common, "required": False})}
    if kind == "place":
        return {spec.name: forms.ChoiceField(choices=[("", "No place")] + _choices("places", "name"), **{**common, "required": False})}
    if kind == "memory":
        if spec.name.endswith("_ids"):
            return {spec.name: forms.MultipleChoiceField(choices=_choices("memories", "title"), widget=forms.CheckboxSelectMultiple, **{**common, "required": False})}
        return {spec.name: forms.ChoiceField(choices=[("", "No memory")] + _choices("memories", "title"), **{**common, "required": False})}
    raise ValueError(f"Unknown field kind {kind}")


def build_form(ct: ContentType, data=None, initial=None) -> forms.Form:
    fields: dict[str, forms.Field] = {}
    for spec in ct.fields:
        fields.update(build_field(spec))
    if ct.publishable:
        fields["is_published"] = forms.BooleanField(label="Published", required=False, initial=True,
                                                    help_text="Unpublished items are hidden from the story.")
        fields["is_public"] = forms.BooleanField(label="Public", required=False,
                                                 help_text="Visible to visitors who are not signed in (only when the public site is enabled).")
    form_class = type(f"{ct.key.title()}Form", (forms.Form,), fields)
    form = form_class(data=data, initial=initial)
    form.content_type = ct
    return form


def _tags(value: str) -> list[str]:
    seen: list[str] = []
    for part in (value or "").split(","):
        tag = " ".join(part.split())[:60]
        if tag and tag.lower() not in [s.lower() for s in seen]:
            seen.append(tag)
    return seen[:30]


def to_document(ct: ContentType, cleaned: dict) -> dict:
    doc: dict = {}
    for spec in ct.fields:
        if spec.kind == "location":
            doc[spec.name] = {part: (cleaned.get(f"{spec.name}__{part}") or "").strip() for part in LOCATION_PARTS}
            continue
        value = cleaned.get(spec.name)
        if spec.kind == "date":
            doc[spec.name] = value.isoformat() if value else ""
        elif spec.kind == "tags":
            doc[spec.name] = _tags(value)
        elif spec.kind == "bool":
            doc[spec.name] = bool(value)
        elif spec.kind in ("photos", "videos") or (spec.kind == "memory" and spec.name.endswith("_ids")):
            doc[spec.name] = list(value or [])
        elif spec.kind in ("int", "float"):
            doc[spec.name] = value
        else:
            doc[spec.name] = value if value is not None else ""
    if ct.publishable:
        doc["is_published"] = bool(cleaned.get("is_published"))
        doc["is_public"] = bool(cleaned.get("is_public"))
    return doc


def to_initial(ct: ContentType, doc: dict) -> dict:
    initial: dict = {}
    for spec in ct.fields:
        value = doc.get(spec.name)
        if spec.kind == "location":
            for part in LOCATION_PARTS:
                initial[f"{spec.name}__{part}"] = (value or {}).get(part, "")
        elif spec.kind == "date":
            initial[spec.name] = parse_iso(value)
        elif spec.kind == "tags":
            initial[spec.name] = ", ".join(value or [])
        else:
            initial[spec.name] = value
    if ct.publishable:
        initial["is_published"] = doc.get("is_published", True) is not False
        initial["is_public"] = bool(doc.get("is_public"))
    return initial


class SettingsForm(forms.Form):
    # Relationship
    person_one = forms.CharField(label="Person one", max_length=80, required=False)
    person_two = forms.CharField(label="Person two", max_length=80, required=False)
    start_date = forms.DateField(label="Relationship start date", required=False, widget=DateInput(format="%Y-%m-%d"),
                                 help_text="Used for the live “Together for” counter.")
    first_meeting_date = forms.DateField(label="First meeting date", required=False, widget=DateInput(format="%Y-%m-%d"))
    anniversary_date = forms.DateField(label="Anniversary date", required=False, widget=DateInput(format="%Y-%m-%d"))
    description = forms.CharField(label="Relationship description", max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    story_intro = forms.CharField(label="How it all started", max_length=10000, required=False, widget=forms.Textarea(attrs={"rows": 8}),
                                  help_text="Shown in the “How It All Started” section. Leave empty until you write it.")
    person_one_photo_id = forms.ChoiceField(label="Person one photo", required=False)
    person_two_photo_id = forms.ChoiceField(label="Person two photo", required=False)
    # Appearance
    hero_title = forms.CharField(label="Hero title", max_length=80, required=False)
    hero_subtitle = forms.CharField(label="Hero subtitle", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    hero_photo_id = forms.ChoiceField(label="Hero image", required=False)
    hero_video_id = forms.ChoiceField(label="Hero background video", required=False, help_text="Plays muted, never with sound.")
    final_quote = forms.CharField(label="Closing line", max_length=200, required=False)
    accent_color = forms.RegexField(label="Accent colour", regex=r"^#[0-9a-fA-F]{6}$", widget=forms.TextInput(attrs={"type": "color"}))
    gold_color = forms.RegexField(label="Gold colour", regex=r"^#[0-9a-fA-F]{6}$", widget=forms.TextInput(attrs={"type": "color"}))
    default_theme = forms.ChoiceField(label="Default theme", choices=(("dark", "Dark (cinematic)"), ("light", "Light")))
    # PWA
    app_name = forms.CharField(label="App name", max_length=45)
    short_name = forms.CharField(label="Short name", max_length=12)
    theme_color = forms.RegexField(label="Theme colour", regex=r"^#[0-9a-fA-F]{6}$", widget=forms.TextInput(attrs={"type": "color"}))
    background_color = forms.RegexField(label="Splash background", regex=r"^#[0-9a-fA-F]{6}$", widget=forms.TextInput(attrs={"type": "color"}))
    # Privacy
    allow_search_indexing = forms.BooleanField(label="Allow search engines", required=False,
                                               help_text="Only has an effect when PUBLIC_SITE_ENABLED=true. Off by default.")
    # Music
    music_enabled = forms.BooleanField(label="Enable music button", required=False, help_text="Music never plays automatically.")
    music_url = forms.URLField(label="Music URL", required=False, assume_scheme="https", help_text="HTTPS link to an MP3/OGG/M4A file you have the right to use.")
    music_title = forms.CharField(label="Music title", max_length=120, required=False)
    # Easter egg
    easter_enabled = forms.BooleanField(label="Enable hidden secret", required=False, help_text="Tap the heart logo five times.")
    easter_message = forms.CharField(label="Secret message", max_length=300, required=False)

    SECTIONS = (
        ("Relationship", ("person_one", "person_two", "start_date", "first_meeting_date", "anniversary_date",
                          "description", "story_intro", "person_one_photo_id", "person_two_photo_id")),
        ("Appearance", ("hero_title", "hero_subtitle", "hero_photo_id", "hero_video_id", "final_quote",
                        "accent_color", "gold_color", "default_theme")),
        ("Install (PWA)", ("app_name", "short_name", "theme_color", "background_color")),
        ("Privacy", ("allow_search_indexing",)),
        ("Music", ("music_enabled", "music_url", "music_title")),
        ("Hidden secret", ("easter_enabled", "easter_message")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        photos = [("", "None")] + _photo_choices()
        for name in ("person_one_photo_id", "person_two_photo_id", "hero_photo_id"):
            self.fields[name].choices = photos
        self.fields["hero_video_id"].choices = [("", "None")] + _choices("videos", "title")

    def clean_music_url(self):
        url = self.cleaned_data.get("music_url", "")
        if url and not url.lower().startswith("https://"):
            raise forms.ValidationError("Use an HTTPS link.")
        return url

    def sections(self):
        return [(title, [self[name] for name in names]) for title, names in self.SECTIONS]

    @classmethod
    def initial_from(cls, s: dict) -> dict:
        rel, app, pwa = s["relationship"], s["appearance"], s["pwa"]
        return {
            **{k: rel.get(k) for k in ("person_one", "person_two", "description", "story_intro",
                                       "person_one_photo_id", "person_two_photo_id")},
            **{k: parse_iso(rel.get(k)) for k in ("start_date", "first_meeting_date", "anniversary_date")},
            **{k: app.get(k) for k in ("hero_title", "hero_subtitle", "hero_photo_id", "hero_video_id", "final_quote",
                                       "accent_color", "gold_color", "default_theme")},
            **{k: pwa.get(k) for k in ("app_name", "short_name", "theme_color", "background_color")},
            "allow_search_indexing": s["privacy"]["allow_search_indexing"],
            "music_enabled": s["music"]["enabled"],
            "music_url": s["music"]["url"],
            "music_title": s["music"]["title"],
            "easter_enabled": s["easter_egg"]["enabled"],
            "easter_message": s["easter_egg"]["message"],
        }

    def to_settings(self) -> dict:
        c = self.cleaned_data

        def iso(key):
            return c[key].isoformat() if c.get(key) else ""

        return {
            "relationship": {
                **{k: (c.get(k) or "").strip() for k in ("person_one", "person_two", "description", "story_intro",
                                                         "person_one_photo_id", "person_two_photo_id")},
                **{k: iso(k) for k in ("start_date", "first_meeting_date", "anniversary_date")},
            },
            "appearance": {k: c.get(k) or "" for k in ("hero_title", "hero_subtitle", "hero_photo_id", "hero_video_id",
                                                       "final_quote", "accent_color", "gold_color", "default_theme")},
            "pwa": {k: c[k] for k in ("app_name", "short_name", "theme_color", "background_color")},
            "privacy": {"allow_search_indexing": bool(c.get("allow_search_indexing"))},
            "music": {"enabled": bool(c.get("music_enabled")), "url": c.get("music_url") or "", "title": c.get("music_title") or ""},
            "easter_egg": {"enabled": bool(c.get("easter_enabled")), "message": c.get("easter_message") or ""},
        }
