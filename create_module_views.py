modules = {
    'timesheets': ('Timesheets Management', '📅'),
    'accounting': ('Accounting & Finance', '💰'),
    'safety': ('Safety Compliance', '🛡️'),
    'equipment': ('Equipment Management', '🏗️'),
    'subcontractors': ('Subcontractors Management', '👷'),
    'blueprints': ('Blueprints & Drawings', '🗺️'),
}

for module, (name, icon) in modules.items():
    class_name = f"{module.capitalize()}DashboardView"

    content = f'''from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


class {class_name}(LoginRequiredMixin, TemplateView):
    """{name} Module Dashboard"""
    template_name = '{module}/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['module_name'] = '{name}'
        context['module_icon'] = '{icon}'
        return context


@login_required
def {module}_dashboard(request):
    """{name} Dashboard view"""
    context = {{
        'module_name': '{name}',
        'module_icon': '{icon}',
    }}
    return render(request, '{module}/dashboard.html', context)
'''

    print(f"# ===== {module}/views.py =====")
    print(content)
    print("\\n" + "=" * 60 + "\\n")
