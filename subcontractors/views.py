from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from projects import readiness
from projects.models import Project
from projects.views_workflow import can_manage_workflow, can_view_project

from .forms import (
    SubcontractorAgreementForm, SubcontractorAgreementLineForm, SubcontractorAgreementPaymentForm,
    SubcontractorGeneralTermsForm,
)
from .models import (
    SubcontractorAgreement, SubcontractorAgreementLine, SubcontractorAgreementPayment, SubcontractorGeneralTerms,
)
from .pdf import generate_subcontractor_agreement_pdf


@login_required
def subcontractors_dashboard(request):
    return render(request, "subcontractors/dashboard.html", {
        "module_name": "Subcontractors Management",
        "module_icon": "👷",
    })


def can_manage_general_terms(user):
    """Company-wide standard clauses that apply to every Musana'a agreement -- same governance as the
    Company Standards & Specifications: admin or the engineering manager."""
    return user.is_admin() or user.is_engineering_manager()


@login_required
def general_terms(request):
    terms = SubcontractorGeneralTerms.load()
    can_manage = can_manage_general_terms(request.user)
    if request.method == 'POST':
        if not can_manage:
            return HttpResponseForbidden("Only an admin or the engineering manager can edit the standard terms.")
        form = SubcontractorGeneralTermsForm(request.POST, instance=terms)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, "Standard terms & conditions updated.")
            return redirect('subcontractors:general_terms')
    else:
        form = SubcontractorGeneralTermsForm(instance=terms)
    return render(request, 'subcontractors/general_terms.html', {
        'terms': terms, 'form': form, 'can_manage': can_manage,
    })


STATUS_ORDER = {'active': 0, 'draft': 1, 'completed': 2, 'terminated': 3}


@login_required
def agreement_list(request):
    agreements = SubcontractorAgreement.objects.select_related('project', 'vendor')
    is_wide_access = request.user.is_admin() or request.user.is_engineering_manager()
    if not is_wide_access:
        if request.user.is_project_manager():
            agreements = agreements.filter(project__manager=request.user)
        else:
            agreements = agreements.none()

    project_id = request.GET.get('project')
    if project_id:
        agreements = agreements.filter(project_id=project_id)

    # Group by project (newest-active project first) instead of one long mixed list, and rank each
    # project's own agreements active-first so the ones still being worked stay on top.
    by_project = {}
    for a in agreements:
        by_project.setdefault(a.project, []).append(a)
    groups = [
        {
            'project': project,
            'agreements': sorted(items, key=lambda a: (STATUS_ORDER.get(a.status, 9), -a.created_at.timestamp())),
            'can_manage': can_manage_workflow(request.user, project),
        }
        for project, items in by_project.items()
    ]
    groups.sort(key=lambda g: max(a.created_at for a in g['agreements']), reverse=True)

    creatable_projects = readiness.ready_projects()
    if not is_wide_access:
        creatable_projects = creatable_projects.filter(manager=request.user) if request.user.is_project_manager() else creatable_projects.none()

    return render(request, 'subcontractors/agreement_list.html', {
        'groups': groups,
        'creatable_projects': creatable_projects.order_by('name'),
        'filtered_project_id': int(project_id) if project_id else None,
    })


@login_required
def agreement_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    form = SubcontractorAgreementForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        agreement = form.save(commit=False)
        agreement.project = project
        agreement.created_by = request.user
        agreement.save()
        messages.success(request, f"Agreement {agreement.agreement_number} created as a draft -- add its BOQ lines, then activate it.")
        return redirect('subcontractors:agreement_detail', pk=agreement.pk)
    return render(request, 'subcontractors/agreement_form.html', {'form': form, 'project': project, 'is_new': True})


@login_required
def agreement_edit(request, pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, agreement.project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    form = SubcontractorAgreementForm(request.POST or None, request.FILES or None, instance=agreement)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"Agreement {agreement.agreement_number} updated.")
        return redirect('subcontractors:agreement_detail', pk=agreement.pk)
    return render(request, 'subcontractors/agreement_form.html', {
        'form': form, 'project': agreement.project, 'agreement': agreement, 'is_new': False,
    })


def _visible_agreement(request, pk):
    agreement = get_object_or_404(SubcontractorAgreement, pk=pk)
    if not can_view_project(request.user, agreement.project):
        return agreement, HttpResponseForbidden("You can't see this agreement.")
    return agreement, None


@login_required
def agreement_detail(request, pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    can_manage = can_manage_workflow(request.user, agreement.project)
    line_form = SubcontractorAgreementLineForm(project=agreement.project)
    payment_form = SubcontractorAgreementPaymentForm()
    return render(request, 'subcontractors/agreement_detail.html', {
        'agreement': agreement,
        'lines': agreement.lines.select_related('sub_item', 'sub_item__phase'),
        'payments': agreement.payments.all(),
        'can_manage': can_manage,
        'line_form': line_form,
        'payment_form': payment_form,
        'terms': SubcontractorGeneralTerms.load(),
    })


@login_required
def agreement_pdf(request, pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    pdf_bytes = generate_subcontractor_agreement_pdf(agreement)
    filename = f"{agreement.agreement_number}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def agreement_status_update(request, pk, new_status):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, agreement.project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    valid_transitions = {
        'draft': {'active'},
        'active': {'completed', 'terminated'},
    }
    if new_status not in dict(SubcontractorAgreement.STATUS) or new_status not in valid_transitions.get(agreement.status, set()):
        messages.error(request, f"Can't move an agreement from '{agreement.status}' to '{new_status}'.")
    else:
        agreement.status = new_status
        agreement.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"Agreement {agreement.agreement_number} is now {agreement.get_status_display()}.")
    return redirect('subcontractors:agreement_detail', pk=agreement.pk)


@login_required
@require_POST
def agreement_line_add(request, pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, agreement.project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    form = SubcontractorAgreementLineForm(request.POST, project=agreement.project)
    if form.is_valid():
        line = form.save(commit=False)
        line.agreement = agreement
        if not line.description:
            line.description = line.sub_item.name_en or line.sub_item.name_ar
        line.save()
        messages.success(request, "Line added.")
    else:
        messages.error(request, "Couldn't add that line: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return redirect('subcontractors:agreement_detail', pk=agreement.pk)


@login_required
@require_POST
def agreement_line_delete(request, pk, line_pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, agreement.project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    line = get_object_or_404(SubcontractorAgreementLine, pk=line_pk, agreement=agreement)
    line.delete()
    messages.success(request, "Line removed.")
    return redirect('subcontractors:agreement_detail', pk=agreement.pk)


@login_required
@require_POST
def agreement_payment_add(request, pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, agreement.project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    form = SubcontractorAgreementPaymentForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.agreement = agreement
        payment.created_by = request.user
        payment.save()
        messages.success(request, "Payment recorded.")
    else:
        messages.error(request, "Couldn't record that payment: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return redirect('subcontractors:agreement_detail', pk=agreement.pk)


@login_required
@require_POST
def agreement_payment_delete(request, pk, payment_pk):
    agreement, denied = _visible_agreement(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, agreement.project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can do this.")
    payment = get_object_or_404(SubcontractorAgreementPayment, pk=payment_pk, agreement=agreement)
    payment.delete()
    messages.success(request, "Payment removed.")
    return redirect('subcontractors:agreement_detail', pk=agreement.pk)
