modules = {
    'crm': 'crm',
    'timesheets': 'timesheets',
    'accounting': 'accounting',
    'safety': 'safety',
    'equipment': 'equipment',
    'subcontractors': 'subcontractors',
    'blueprints': 'blueprints',
}

for app, module in modules.items():
    content = f"""from django.urls import path
from . import views

app_name = '{app}'

urlpatterns = [
    path('', views.{module}_dashboard, name='dashboard'),
]
"""

    filepath = f"{app}\\urls.py"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✓ {filepath}")
