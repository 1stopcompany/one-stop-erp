from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def equipment_dashboard(request):
    return render(request, "equipment/dashboard.html", {
        "module_name": "Equipment Management",
        "module_icon": "🏗️",
    })
