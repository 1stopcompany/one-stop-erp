"""Management print-outs that belong to the project BOQ."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from projects.models import Project

from .boq_pdf import generate_boq_pdf


def can_print_management_reports(user, project):
    """The BOQ and cost print-outs show cost prices and margins: management only (and the project's own manager)."""
    if user.is_anonymous:
        return False
    if user.is_admin() or user.is_general_manager() or user.is_engineering_manager():
        return True
    return user.is_project_manager() and project.manager_id == user.id


@login_required
@require_http_methods(["GET"])
def boq_pdf(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_print_management_reports(request.user, project):
        return HttpResponseForbidden("The BOQ print-out is for management.")
    response = HttpResponse(generate_boq_pdf(project), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="BOQ-{project.project_symbol}.pdf"'
    return response
