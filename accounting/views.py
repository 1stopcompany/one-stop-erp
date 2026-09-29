from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def accounting_dashboard(request):
    return render(request, "accounting/dashboard.html", {
        "module_name": "Accounting & Finance",
        "module_icon": "💰",
    })
