"""Admin -> Import History: upload, candidate list and per-candidate review."""
from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.dates import parse_iso
from apps.core.ratelimit import rate_limit
from apps.core.registry import FIRST_KEYS, IMPORTANCE, TIMELINE_CATEGORIES
from apps.core.repository import repo
from apps.dashboard.decorators import staff_required
from apps.dashboard.forms import DateInput, _tags

from . import services

STATUSES = ("pending", "approved", "merged", "rejected")


class UploadForm(forms.Form):
    file = forms.FileField(label="Conversation file", help_text="TXT, MD, JSON, HTML or PDF.")


class ReviewForm(forms.Form):
    target = forms.ChoiceField(label="Save as", choices=list(services.TARGETS.items()))
    title = forms.CharField(max_length=300, required=False)
    date = forms.DateField(required=False, widget=DateInput(format="%Y-%m-%d"),
                           help_text="Leave empty if the date is unknown.")
    category = forms.ChoiceField(choices=TIMELINE_CATEGORIES, required=False)
    importance = forms.ChoiceField(choices=IMPORTANCE, required=False)
    first_key = forms.ChoiceField(label="Marks our first…", choices=(("", "Not a first"),) + FIRST_KEYS, required=False)
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), max_length=20000, required=False)
    quote = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), max_length=1000, required=False)
    sender = forms.CharField(label="Said by", max_length=120, required=False, help_text="For messages only.")
    location_name = forms.CharField(label="Place", max_length=200, required=False)
    location_city = forms.CharField(label="City", max_length=200, required=False)
    location_country = forms.CharField(label="Country", max_length=200, required=False)
    people = forms.CharField(max_length=500, required=False, help_text="Comma separated.")
    tags = forms.CharField(max_length=500, required=False, help_text="Comma separated.")

    @classmethod
    def initial_from(cls, pending: dict) -> dict:
        s = pending.get("suggested") or {}
        loc = s.get("location") or {}
        return {
            "target": pending.get("target"),
            **{k: s.get(k, "") for k in ("title", "category", "importance", "first_key", "description", "quote", "sender")},
            "date": parse_iso(s.get("date")),
            "location_name": loc.get("name", ""),
            "location_city": loc.get("city", ""),
            "location_country": loc.get("country", ""),
            "people": ", ".join(s.get("people") or []),
            "tags": ", ".join(s.get("tags") or []),
        }

    def suggestion(self) -> dict:
        c = self.cleaned_data
        return {
            **{k: (c.get(k) or "").strip() for k in ("title", "category", "importance", "first_key", "quote", "sender")},
            "description": (c.get("description") or "").strip(),
            "date": c["date"].isoformat() if c.get("date") else "",
            "location": {"name": c.get("location_name", "").strip(), "city": c.get("location_city", "").strip(),
                         "country": c.get("location_country", "").strip()},
            "people": _tags(c.get("people", "")),
            "tags": _tags(c.get("tags", "")),
        }


@staff_required
@require_http_methods(["GET", "POST"])
@rate_limit("import", limit=20, window=60 * 10)
def index(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        if upload.size > settings.MAX_IMPORT_UPLOAD_MB * 1024 * 1024:
            form.add_error("file", f"Files must be under {settings.MAX_IMPORT_UPLOAD_MB} MB.")
        else:
            job = services.run_import(upload.name, upload.read(), request.user)
            if job["status"] == "failed":
                messages.error(request, job["error"])
                return redirect("imports:index")
            found = job["stats"].get("candidates", 0)
            messages.success(request, f"Found {found} possible memories. Nothing is published until you approve it.")
            return redirect("imports:job", job_id=job["id"])
    jobs = repo("import_jobs").find({}, sort=(("created_at", -1),), limit=30)
    for job in jobs:
        job["pending"] = repo("pending_memories").count({"job_id": job["id"], "status": "pending"})
    return render(request, "dashboard/imports/index.html", {
        "form": form, "jobs": jobs, "max_mb": settings.MAX_IMPORT_UPLOAD_MB,
        "pending_total": repo("pending_memories").count({"status": "pending"}),
    })


@staff_required
def job_detail(request, job_id: str):
    job = repo("import_jobs").get(job_id)
    if not job:
        raise Http404
    status = request.GET.get("status", "pending")
    status = status if status in STATUSES else "pending"
    confidence = request.GET.get("confidence", "")
    query: dict = {"job_id": job_id, "status": status}
    if confidence in ("low", "medium", "high"):
        query["confidence"] = confidence
    items = repo("pending_memories").find(query, sort=(("suggested.date", 1), ("created_at", 1)), limit=500)
    counts = {s: repo("pending_memories").count({"job_id": job_id, "status": s}) for s in STATUSES}
    return render(request, "dashboard/imports/job.html", {
        "job": job, "items": items, "status": status, "confidence": confidence, "counts": counts,
        "targets": services.TARGETS,
    })


@staff_required
@require_http_methods(["GET", "POST"])
def review(request, pending_id: str):
    pending = repo("pending_memories").get(pending_id)
    if not pending:
        raise Http404
    duplicates = pending.get("possible_duplicates") or []
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reject":
            services.reject(pending_id)
            messages.success(request, "Rejected. It will not appear anywhere.")
            return _next_pending(request, pending)
        form = ReviewForm(request.POST)
        if form.is_valid():
            suggestion = form.suggestion()
            if action == "save":
                repo("pending_memories").update(pending_id, {"suggested": suggestion, "target": form.cleaned_data["target"]})
                messages.success(request, "Changes saved. Still waiting for approval.")
                return redirect("imports:review", pending_id=pending_id)
            if action == "merge":
                collection, _, target_id = (request.POST.get("merge_into") or "").partition(":")
                if services.merge(pending, suggestion, collection, target_id):
                    messages.success(request, "Merged into the existing memory.")
                    return _next_pending(request, pending)
                messages.error(request, "Choose an existing memory to merge into.")
            elif action == "approve":
                new_id, errors = services.approve(pending, suggestion, form.cleaned_data["target"])
                if new_id:
                    messages.success(request, "Approved and added to your story.")
                    return _next_pending(request, pending)
                for err in errors:
                    messages.error(request, err)
    else:
        form = ReviewForm(initial=ReviewForm.initial_from(pending))
    job = repo("import_jobs").get(pending.get("job_id"))
    return render(request, "dashboard/imports/review.html", {
        "pending": pending, "form": form, "duplicates": duplicates, "job": job,
    })


def _next_pending(request, pending: dict):
    nxt = repo("pending_memories").find(
        {"job_id": pending["job_id"], "status": "pending"}, sort=(("suggested.date", 1), ("created_at", 1)), limit=1
    )
    if nxt and request.POST.get("continue") != "0":
        return redirect("imports:review", pending_id=nxt[0]["id"])
    return redirect("imports:job", job_id=pending["job_id"])


@staff_required
@require_POST
def bulk(request, job_id: str):
    action = request.POST.get("action")
    ids = request.POST.getlist("ids")
    if action == "reject_selected":
        for pid in ids[:500]:
            doc = repo("pending_memories").get(pid, {"job_id": job_id, "status": "pending"})
            if doc:
                services.reject(pid)
        messages.success(request, f"Rejected {len(ids)} candidates.")
    elif action == "reject_low":
        result = repo("pending_memories").col.update_many(
            {"job_id": job_id, "status": "pending", "confidence": "low"}, {"$set": {"status": "rejected"}}
        )
        messages.success(request, f"Rejected {result.modified_count} low-confidence candidates.")
    elif action == "delete_job":
        repo("pending_memories").col.delete_many({"job_id": job_id, "status": {"$in": ["pending", "rejected"]}})
        repo("import_jobs").delete(job_id)
        messages.success(request, "Import removed. Approved memories were kept.")
        return redirect("imports:index")
    return redirect("imports:job", job_id=job_id)
