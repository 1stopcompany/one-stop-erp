"""Which sections of the company standard (One Stop Standards and Specifications) apply to a given
project, based on its own nature -- e.g. a project with no subcontractors leaves that section off."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from core.models import SpecificationSection, SpecificationVolume

from .models import Project
from .views_workflow import can_manage_workflow, can_view_project


@login_required
def project_specifications(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_view_project(request.user, project):
        return HttpResponseForbidden("You can't see this project.")
    volumes = SpecificationVolume.objects.prefetch_related('sections')
    applicable_ids = set(project.applicable_spec_sections.values_list('pk', flat=True))
    return render(request, 'projects/project_specifications.html', {
        'project': project,
        'volumes': volumes,
        'applicable_ids': applicable_ids,
        'can_manage': can_manage_workflow(request.user, project),
    })


@login_required
@require_POST
def project_specification_toggle(request, pk, section_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    section = get_object_or_404(SpecificationSection, pk=section_pk)
    if project.applicable_spec_sections.filter(pk=section.pk).exists():
        project.applicable_spec_sections.remove(section)
        applicable = False
    else:
        project.applicable_spec_sections.add(section)
        applicable = True
    return JsonResponse({'applicable': applicable})
