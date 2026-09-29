from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


class CRMDashboardView(LoginRequiredMixin, TemplateView):
    """CRM Module Dashboard"""
    template_name = 'crm/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['module_name'] = 'Customer Relationship Management (CRM)'
        context['module_icon'] = '🤝'
        return context


@login_required
def crm_dashboard(request):
    """CRM Dashboard view"""
    context = {
        'module_name': 'Customer Relationship Management (CRM)',
        'module_icon': '🤝',
    }
    return render(request, 'crm/dashboard.html', context)