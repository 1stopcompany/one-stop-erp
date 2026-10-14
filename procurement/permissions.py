"""
Who may see and do what in Procurement (web pages, the REST API and the phone use the same rules).

    items (the catalogue)   everyone who works with procurement SEES them; only the procurement officers and the admin DEFINE, edit or delete them
                            -- a project manager / site engineer asks for an item that exists, he never creates a new one
    vendors                 seen by admin, managers, procurement, accountant; created / edited only by procurement and admin
    requisitions (PR)       site engineer: his projects'; project manager: his projects' (+ approves); procurement: approved ones and his own;
                            engineering / general manager: all (read only); admin: all
    RFQ                     procurement and admin work them; engineering / general manager read
    purchase orders         procurement, store, accountant, managers, admin see all; site engineer / project manager only their projects'
    receipts                recorded by procurement, storekeeper, the project's engineer and admin; corrected only by procurement / admin
"""
from django.db.models import Q

# every role that uses the procurement pages at all (an ordinary employee does not)
VIEW_ROLES = {'admin', 'general_manager', 'engineering_manager', 'project_manager', 'site_engineer', 'procurement_officer', 'storekeeper', 'accountant'}
CATALOG_ROLES = {'admin', 'procurement_officer'}
VENDOR_VIEW_ROLES = {'admin', 'general_manager', 'engineering_manager', 'procurement_officer', 'accountant'}
RFQ_VIEW_ROLES = {'admin', 'general_manager', 'engineering_manager', 'procurement_officer'}
ORDER_VIEW_ROLES = VIEW_ROLES
RECEIPT_ROLES = {'admin', 'procurement_officer', 'storekeeper', 'site_engineer'}


def _role_ok(user, roles):
    if not user or not user.is_authenticated:
        return False
    return user.is_admin() or user.role in roles


def can_view_procurement(user):
    return _role_ok(user, VIEW_ROLES)


def can_manage_catalog(user):
    """Define / edit / delete catalogue items (and the same for vendors): procurement and admin only."""
    return _role_ok(user, CATALOG_ROLES)


def can_view_vendors(user):
    return _role_ok(user, VENDOR_VIEW_ROLES)


def can_view_rfq(user):
    return _role_ok(user, RFQ_VIEW_ROLES)


def can_view_orders(user):
    return _role_ok(user, ORDER_VIEW_ROLES)


def can_record_receipts(user):
    return _role_ok(user, RECEIPT_ROLES)


def scoped_prs(user, qs):
    """The requisitions this user may see."""
    if user.is_admin() or user.is_engineering_manager() or user.is_general_manager():
        return qs
    if user.is_procurement_officer():
        return qs.filter(Q(requested_by=user) | Q(status__in=['approved', 'in_procurement', 'completed']))
    if user.is_site_engineer():
        return qs.filter(Q(project__site_engineer=user) | Q(requested_by=user))
    if user.is_project_manager():
        return qs.filter(Q(project__manager=user) | Q(project__site_engineer=user))
    return qs.none()


def scoped_pos(user, qs):
    """The purchase orders this user may see."""
    if user.is_admin() or user.is_procurement_officer() or user.is_storekeeper() or user.is_accountant() \
            or user.is_engineering_manager() or user.is_general_manager():
        return qs
    if user.is_site_engineer():
        return qs.filter(project__site_engineer=user)
    if user.is_project_manager():
        return qs.filter(Q(project__manager=user) | Q(project__site_engineer=user))
    return qs.none()
