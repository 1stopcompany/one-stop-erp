"""
Turns the readiness rule (projects/readiness.py) on for the length of every web request, and turns the
exception it raises into a clear answer: a message and a redirect for pages, a 403 with the message for AJAX/API calls.
(DRF views render the exception themselves as a 403.)
"""
from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse

from . import readiness


def _wants_json(request) -> bool:
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
        or request.content_type == "application/json"
        or "/api/" in request.path
    )


class ProjectReadinessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with readiness.request_scope():
            return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, readiness.ProjectNotReady):
            return None
        if _wants_json(request):
            return JsonResponse({"error": exception.message, "blocked": True, "project_id": exception.project.pk}, status=403)
        messages.error(request, exception.message)
        target = reverse("projects:workflow", args=[exception.project.pk])
        return HttpResponseRedirect(target)
