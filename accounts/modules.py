"""
Which parts of the ERP a role may open at all (on top of the rules inside each part).

Most roles see every module as before. The procurement officer and the accountant are limited to the sections their work needs:

    procurement_officer   Procurement only
    accountant            Procurement (read only -- see procurement/permissions.py) and Accounting

The limit is applied in three places that always agree: the menu and the home dashboard (the `modules` template variable), and this
middleware, which refuses a web page of any other module (a typed address does not get around it). Token calls from the phone are
not touched (they have their own permission checks), nor is the admin.
"""
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.urls import reverse

# module key -> the URL prefix it lives under
MODULE_PREFIXES = {
    'projects': '/projects/',
    'reports': '/reports/',
    'core': '/core/',
    'timesheets': '/timesheets/',
    'procurement': '/procurement/',
    'cost_control': '/cost_control/',
    'crm': '/crm/',
    'accounting': '/accounting/',
    'safety': '/safety/',
    'equipment': '/equipment/',
    'subcontractors': '/subcontractors/',
    'blueprints': '/blueprints/',
    'ai': '/ai/',
}

ROLE_MODULES = {
    'procurement_officer': {'procurement'},
    'accountant': {'procurement', 'accounting'},
}


# single pages of another module a role needs: the accountant reads the equipment rental claims he pays from the Accounting "Payables" page
ROLE_EXTRA_PREFIXES = {
    'accountant': ('/equipment/claims/',),
}


def allowed_modules(user):
    """The set of module keys the user may open, or None when nothing is limited."""
    if not user or not user.is_authenticated or user.is_admin():
        return None
    return ROLE_MODULES.get(user.role)


class ModuleMap(dict):
    """`modules.crm` in a template: True when the user may open it (always True for a role that is not limited)."""

    def __init__(self, allowed):
        super().__init__({key: (allowed is None or key in allowed) for key in MODULE_PREFIXES})

    def __missing__(self, key):
        return True


def module_access(request):
    return {'modules': ModuleMap(allowed_modules(getattr(request, 'user', None)))}


class ModuleAccessMiddleware:
    """Refuses the pages of a module the signed-in user's role may not open (browser sessions only)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = allowed_modules(getattr(request, 'user', None))
        if allowed is not None:
            extra = ROLE_EXTRA_PREFIXES.get(request.user.role, ())
            for key, prefix in MODULE_PREFIXES.items():
                if request.path.startswith(prefix) and key not in allowed and not request.path.startswith(extra):
                    wants_json = ('/api/' in request.path or request.headers.get('x-requested-with') == 'XMLHttpRequest'
                                  or 'application/json' in request.headers.get('accept', ''))
                    if wants_json:
                        return JsonResponse({'detail': 'Your account cannot open this part of the system.'}, status=403)
                    if request.method == 'GET':
                        messages.error(request, 'Your account cannot open this part of the system.')
                        return HttpResponseRedirect(reverse('dashboard'))
                    return HttpResponseForbidden('Your account cannot open this part of the system.')
        return self.get_response(request)
