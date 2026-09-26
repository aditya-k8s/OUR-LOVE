from django import template
from django.urls import reverse

from apps.core.registry import CONTENT_TYPES
from apps.core.repository import repo

register = template.Library()

SECTIONS = [
    ("Story", [("timeline", "story"), ("memories", "memories"), ("letters", "letter"), ("messages", "quote")]),
    ("Media", [("photos", "gallery"), ("videos", "video")]),
    ("Details", [("places", "pin"), ("gifts", "gift"), ("dates", "calendar"), ("future", "future")]),
]


@register.inclusion_tag("dashboard/partials/nav.html", takes_context=True)
def dashboard_nav(context):
    path = context["request"].path
    groups = []
    for title, items in SECTIONS:
        links = []
        for key, icon in items:
            ct = CONTENT_TYPES[key]
            url = reverse("dashboard:list", args=[key])
            links.append({"url": url, "label": ct.label_plural, "icon": icon, "active": path.startswith(url),
                          "count": repo(ct.collection).count()})
        groups.append({"title": title, "links": links})
    import_url = reverse("imports:index")
    return {
        "home_active": path == reverse("dashboard:home"),
        "groups": groups,
        "pending": repo("pending_memories").count({"status": "pending"}),
        "import_url": import_url,
        "import_active": path.startswith(import_url),
        "settings_active": path.startswith(reverse("dashboard:settings")),
        "export_active": path.startswith(reverse("dashboard:export")),
        "csrf_token": context.get("csrf_token"),
    }
