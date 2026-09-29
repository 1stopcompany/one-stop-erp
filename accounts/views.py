from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db.models import Q
from .models import CustomUser, UserAuditLog
from .forms import UserCreationForm, UserChangeForm, LoginForm
import logging

logger = logging.getLogger(__name__)


@login_required
def user_profile(request):
    """
    Display the current user's profile.
    """
    return render(request, 'accounts/user_profile.html', {
        'user': request.user,
    })

@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                # Log the login action
                UserAuditLog.objects.create(
                    user=user,
                    action='login',
                    content_type='User',
                    description=f'User {user.username} logged in',
                    ip_address=get_client_ip(request),
                )
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


@login_required
@require_http_methods(["POST"])
def logout_view(request):
    """User logout view"""
    UserAuditLog.objects.create(
        user=request.user,
        action='logout',
        content_type='User',
        description=f'User {request.user.username} logged out',
        ip_address=get_client_ip(request),
    )
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('accounts:login')


def is_admin(user):
    """Check if user is admin"""
    return user.is_authenticated and user.is_admin()


def is_project_manager(user):
    """Check if user is project manager"""
    return user.is_authenticated and user.is_project_manager()


def is_site_engineer(user):
    """Check if user is site engineer"""
    return user.is_authenticated and user.is_site_engineer()


class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all users (Admin only)"""
    model = CustomUser
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    paginate_by = 20
    
    def test_func(self):
        return self.request.user.is_admin()
    
    def get_queryset(self):
        queryset = CustomUser.objects.all()
        search = self.request.GET.get('search')
        role = self.request.GET.get('role')
        
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
        
        if role:
            queryset = queryset.filter(role=role)
        
        return queryset.order_by('-created_at')


class UserDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """View user details"""
    model = CustomUser
    template_name = 'accounts/user_detail.html'
    context_object_name = 'user_obj'
    
    def test_func(self):
        user = self.get_object()
        return self.request.user.is_admin() or self.request.user == user


class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create new user (Admin only)"""
    model = CustomUser
    form_class = UserCreationForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    
    def test_func(self):
        return self.request.user.is_admin()
    
    def form_valid(self, form):
        response = super().form_valid(form)
        UserAuditLog.objects.create(
            user=self.request.user,
            action='create',
            content_type='CustomUser',
            object_id=self.object.id,
            description=f'Created user {self.object.username}',
            ip_address=get_client_ip(self.request),
        )
        messages.success(self.request, f'User {self.object.username} created successfully.')
        return response


class UserUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update user (Admin or self)"""
    model = CustomUser
    form_class = UserChangeForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    
    def test_func(self):
        user = self.get_object()
        return self.request.user.is_admin() or self.request.user == user
    
    def form_valid(self, form):
        response = super().form_valid(form)
        UserAuditLog.objects.create(
            user=self.request.user,
            action='update',
            content_type='CustomUser',
            object_id=self.object.id,
            description=f'Updated user {self.object.username}',
            ip_address=get_client_ip(self.request),
        )
        messages.success(self.request, f'User {self.object.username} updated successfully.')
        return response


@login_required
def dashboard_view(request):
    """
    Administration overview (admin only). Everyone else has no separate "role dashboard" any
    more -- their work lives on the main ERP dashboard and the Site Reports hub -- so this
    sends them there instead of showing a near-copy of it.
    """
    user = request.user
    if not user.is_admin():
        if user.is_engineering_manager() or user.is_general_manager():
            return redirect('reports:approvals_dashboard')
        return redirect('dashboard')

    from projects.models import Project
    from reports.models import DailyReport, MonthlyReport
    from reports.owner_financial_models import OwnerFinancialReport

    report_models = (DailyReport, MonthlyReport, OwnerFinancialReport)
    context = {
        'user': user,
        'total_users': CustomUser.objects.count(),
        'total_projects': Project.objects.count(),
        'total_reports': sum(m.objects.count() for m in report_models),
        # Waiting on either approval stage (engineering manager, then general manager).
        'pending_approvals': sum(
            m.objects.filter(status__in=['submitted', 'engineering_approved']).count() for m in report_models
        ),
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
