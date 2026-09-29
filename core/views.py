from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import SpecificationSectionForm, SpecificationVolumeForm
from .models import SpecificationSection, SpecificationVolume
from .pdf import generate_specification_section_pdf


@login_required
def erp_dashboard(request):
    return render(request, 'erp_dashboard.html')


def can_manage_specifications(user):
    """Upload/delete volumes: admin or engineering manager -- the same roles that own drawings/specs company-wide."""
    return user.is_admin() or user.is_engineering_manager()


@login_required
def specifications_list(request):
    volumes = list(SpecificationVolume.objects.prefetch_related('sections'))
    return render(request, 'core/specifications_list.html', {
        'volumes': volumes,
        'can_manage': can_manage_specifications(request.user),
    })


@login_required
def specification_volume_add(request):
    if not can_manage_specifications(request.user):
        return HttpResponseForbidden("Only an admin or the engineering manager can add a specification volume.")
    form = SpecificationVolumeForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        volume = form.save(commit=False)
        volume.uploaded_by = request.user
        volume.save()
        messages.success(request, f"'{volume.label}' uploaded.")
        return redirect('core:specifications_list')
    return render(request, 'core/specification_volume_form.html', {'form': form})


@login_required
def specification_section_add(request, volume_pk):
    if not can_manage_specifications(request.user):
        return HttpResponseForbidden("Only an admin or the engineering manager can add a specification section.")
    volume = get_object_or_404(SpecificationVolume, pk=volume_pk)
    form = SpecificationSectionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        section = form.save(commit=False)
        section.volume = volume
        section.save()
        messages.success(request, f"'{section.code} - {section.title}' added to {volume.label}.")
        return redirect('core:specifications_list')
    return render(request, 'core/specification_section_form.html', {
        'form': form, 'volume': volume, 'is_new': True,
    })


@login_required
def specification_section_edit(request, pk):
    if not can_manage_specifications(request.user):
        return HttpResponseForbidden("Only an admin or the engineering manager can edit a specification section.")
    section = get_object_or_404(SpecificationSection, pk=pk)
    form = SpecificationSectionForm(request.POST or None, instance=section)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"'{section.code} - {section.title}' updated.")
        return redirect('core:specifications_list')
    return render(request, 'core/specification_section_form.html', {
        'form': form, 'volume': section.volume, 'is_new': False, 'section': section,
    })


@login_required
def specification_section_detail(request, pk):
    """JSON for the section's popup card (title, volume, body text)."""
    section = get_object_or_404(SpecificationSection, pk=pk)
    return JsonResponse({
        'code': section.code,
        'title': section.title,
        'volume_label': section.volume.label,
        'volume_title': section.volume.title,
        'content': section.content,
        'pdf_url': f"/core/specifications/sections/{section.pk}/pdf/",
        'edit_url': f"/core/specifications/sections/{section.pk}/edit/",
        'can_manage': can_manage_specifications(request.user),
    })


@login_required
def specification_section_pdf(request, pk):
    """This one section only, as its own small PDF -- not the whole volume."""
    section = get_object_or_404(SpecificationSection, pk=pk)
    pdf_bytes = generate_specification_section_pdf(section)
    filename = f"{section.code} - {section.title}.pdf".replace('/', '-')
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def specification_volume_delete(request, pk):
    if not can_manage_specifications(request.user):
        return HttpResponseForbidden("Only an admin or the engineering manager can delete a specification volume.")
    volume = get_object_or_404(SpecificationVolume, pk=pk)
    volume.document.delete(save=False)
    volume.delete()
    messages.success(request, "Volume deleted.")
    return redirect('core:specifications_list')
