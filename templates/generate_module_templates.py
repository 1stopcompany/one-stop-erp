import os

modules = [
    "crm",
    "timesheets",
    "accounting",
    "safety",
    "equipment",
    "subcontractors",
    "blueprints",
    "procurement",
    "cost_control",
]

template = r"""{% extends 'module_base.html' %}

{% block title %}{{ module_name }} - ERP System{% endblock %}

{% block content %}
<div class="container-fluid mt-5">

  <div class="row mb-4">
    <div class="col-md-12">
      <div class="card border-0 shadow-sm">
        <div class="card-body d-flex justify-content-between align-items-center">
          <div>
            <h1 class="mb-0">
              <span style="font-size:2.5rem;">{{ module_icon }}</span>
              {{ module_name }}
            </h1>
            <p class="text-muted mt-2">
              Manage all {{ module_name|lower }} operations
            </p>
          </div>
          <a href="{% url 'dashboard' %}" class="btn btn-outline-secondary">
            <i class="bi bi-house"></i> Back to Dashboard
          </a>
        </div>
      </div>
    </div>
  </div>

  <div class="card border-0 shadow-sm">
    <div class="card-body">
      <div class="alert alert-info mb-0">
        <i class="bi bi-info-circle"></i>
        <strong>Module Status:</strong> {{ module_name }} module is under development.
      </div>
    </div>
  </div>

  <div class="row mt-4">
    <div class="col-md-12">
      <div class="card border-0 shadow-sm">
        <div class="card-body d-flex gap-2 flex-wrap">
          <a href="{% url 'dashboard' %}" class="btn btn-outline-primary">
            <i class="bi bi-speedometer2"></i> Dashboard
          </a>
          <a href="{% url 'projects:project_list' %}" class="btn btn-outline-primary">
            <i class="bi bi-building"></i> Projects
          </a>
          <a href="{% url 'reports:report_type_selection' %}" class="btn btn-outline-primary">
            <i class="bi bi-file-text"></i> Reports
          </a>
        </div>
      </div>
    </div>
  </div>

</div>
{% endblock %}
"""

for module in modules:
    os.makedirs(module, exist_ok=True)
    path = os.path.join(module, "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(template)
    print(f"✓ {path}")
