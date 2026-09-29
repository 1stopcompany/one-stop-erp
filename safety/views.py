from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def safety_dashboard(request):
    return render(request, "safety/dashboard.html", {
        "module_name": "Safety Compliance",
        "module_icon": "🛡️",
    })
