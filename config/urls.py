"""
Main URL Configuration for Site Engineer Reports / One Stop ERP System (Merged)
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

# DRF token auth
from rest_framework.authtoken.views import obtain_auth_token

from core.views import erp_dashboard

# (اختياري) لو عندك القيم هاي في settings
admin.site.site_header = getattr(settings, "ADMIN_SITE_HEADER", "One Stop Contracting Co.")
admin.site.site_title = getattr(settings, "ADMIN_SITE_TITLE", "ERP System Administration")
admin.site.index_title = getattr(settings, "ADMIN_INDEX_TITLE", "Welcome")

@require_http_methods(["GET"])
def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('accounts:login')


urlpatterns = [
    # Home + Dashboard
    path('', home_view, name='home'),
    path('Dashboard/', erp_dashboard, name='dashboard'),

    # Admin
    path('admin/', admin.site.urls),

    # API Authentication (الجديد)
    path('api-token-auth/', obtain_auth_token, name='api_token_auth'),
    path('api-auth/', include('rest_framework.urls')),

    # Core apps
    path('accounts/', include('accounts.urls')),
    path('projects/', include('projects.urls')),
    path('reports/', include('reports.urls')),
    path('core/', include('core.urls')),

    # ERP modules
    # ERP modules (FIXED – no tuple include, no duplicate namespace)
    path('timesheets/', include('timesheets.urls')),
    path('procurement/', include('procurement.urls')),
    path('cost_control/', include('cost_control.urls')),
    path('crm/', include('crm.urls')),
    path('accounting/', include('accounting.urls')),
    path('safety/', include('safety.urls')),
    path('equipment/', include('equipment.urls')),
    path('subcontractors/', include('subcontractors.urls')),
    path('blueprints/', include('blueprints.urls')),
    path('ai/', include('ai_assistant.urls')),
]

# `static` was imported above but never wired in -- uploaded media
# (report attachments, phase photos, ...) saved fine but 404'd when
# served back, since Django's dev server never serves MEDIA_ROOT without
# this. Production still serves media via the web server/Nginx, not this.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.STORAGES['default']['BACKEND'] == 'django.core.files.storage.FileSystemStorage':
    # Production with the files on this server's own disk (no Dropbox): shared hosting like cPanel does not serve /media/ by itself, so
    # the uploaded photos / documents came back as broken images. Serve them through Django, but ONLY to logged-in users (the files
    # include identity documents and contracts, so they must never be open to anyone who has the address).
    from django.contrib.auth.decorators import login_required
    from django.urls import re_path
    from django.views.static import serve as _serve_media

    urlpatterns += [
        re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), login_required(_serve_media), {'document_root': settings.MEDIA_ROOT}),
    ]