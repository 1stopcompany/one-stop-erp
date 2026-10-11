"""
The "Login account" part of the employee add / edit page: create the employee's system user, link an existing one, or (when the
employee already has one) change its role, password and active flag -- without going to the Django admin.

Who may give which role: HR managers can give the ordinary working roles; the roles that see everything or approve across projects
(admin, general manager, engineering manager) can only be given -- or taken away -- by an administrator, so this page cannot be used to
raise anyone's (or one's own) privileges. An administrator's own account is only editable here by an administrator.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()

# roles only an administrator may hand out or change
ADMIN_ONLY_ROLES = {'admin', 'general_manager', 'engineering_manager'}

MODE_NONE, MODE_CREATE, MODE_LINK = 'none', 'create', 'link'


class EmployeeAccountForm(forms.Form):
    mode = forms.ChoiceField(required=False, choices=[(MODE_NONE, 'No account'), (MODE_CREATE, 'Create a new account'), (MODE_LINK, 'Link an existing user')])
    username = forms.CharField(required=False, max_length=150)
    password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}))
    role = forms.ChoiceField(required=False)
    existing_user = forms.ModelChoiceField(required=False, queryset=User.objects.none())
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, employee=None, acting_user=None, **kwargs):
        kwargs.setdefault('prefix', 'acct')
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'is_active':
                field.widget.attrs['class'] = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
        self.employee = employee if employee is not None and employee.pk else None
        self.acting_user = acting_user
        self.user = self.employee.user if self.employee and self.employee.user_id else None
        is_admin = bool(acting_user and acting_user.is_admin())
        self.can_assign_all = is_admin
        self.fields['role'].choices = [(value, label) for value, label in User.USER_ROLES if is_admin or value not in ADMIN_ONLY_ROLES]
        # a user is shown (and may be changed) only if it is not an admin-level one, unless the person editing is an administrator
        self.locked = bool(self.user and not is_admin and (self.user.is_superuser or self.user.role in ADMIN_ONLY_ROLES))
        linkable = User.objects.filter(employee_profile__isnull=True, is_active=True).order_by('username')
        if not is_admin:
            linkable = linkable.filter(is_superuser=False).exclude(role__in=ADMIN_ONLY_ROLES)
        self.fields['existing_user'].queryset = linkable
        self.fields['existing_user'].label_from_instance = lambda u: f'{u.username} ({u.get_role_display()})'
        if self.user and not self.is_bound:
            self.initial.update({'role': self.user.role, 'is_active': self.user.is_active})

    # ------------------------------------------------------------------ validation
    def clean(self):
        data = super().clean()
        if self.locked:   # an administrator-level account is shown read-only; nothing in this section is applied
            return data
        password = data.get('password')
        if self.user:
            self._clean_role(data)
            if password:
                self._validate_password(password, self.user)
            return data
        mode = data.get('mode') or MODE_NONE
        if mode == MODE_CREATE:
            username = (data.get('username') or '').strip()
            if not username:
                self.add_error('username', 'Choose a username.')
            elif User.objects.filter(username__iexact=username).exists():
                self.add_error('username', 'This username is already taken.')
            if not password:
                self.add_error('password', 'Set a password for the new account.')
            else:
                self._validate_password(password, None)
            if not data.get('role'):
                self.add_error('role', 'Choose a role.')
            else:
                self._clean_role(data)
        elif mode == MODE_LINK:
            if not data.get('existing_user'):
                self.add_error('existing_user', 'Choose the user to link.')
        return data

    def _clean_role(self, data):
        role = data.get('role')
        if role and role not in dict(self.fields['role'].choices):
            self.add_error('role', 'You cannot give this role.')

    def _validate_password(self, password, user):
        try:
            validate_password(password, user)
        except ValidationError as error:
            self.add_error('password', error)

    # ------------------------------------------------------------------ save
    def save(self, employee):
        """Apply the chosen action to the (already saved) employee. Returns a short text for the success message, or ''."""
        from accounts.models import UserAuditLog
        if self.locked:
            return ''
        data = self.cleaned_data
        user, text = None, ''
        if self.user:
            user = self.user
            changes = []
            if data.get('role') and data['role'] != user.role:
                user.role = data['role']
                changes.append(f'role -> {user.get_role_display()}')
            if bool(data.get('is_active')) != user.is_active:
                user.is_active = bool(data.get('is_active'))
                changes.append('activated' if user.is_active else 'deactivated')
            if data.get('password'):
                user.set_password(data['password'])
                changes.append('password changed')
            if changes:
                user.save()
                text = f'Account {user.username}: ' + ', '.join(changes) + '.'
                UserAuditLog.objects.create(user=self.acting_user, action='update', content_type='accounts.CustomUser', object_id=user.pk,
                                            description=f'Employee page: {user.username} ' + ', '.join(changes))
        else:
            mode = data.get('mode') or MODE_NONE
            if mode == MODE_CREATE:
                user = User.objects.create_user(
                    username=data['username'].strip(), password=data['password'], role=data['role'], email=employee.email or '',
                    first_name=employee.first_name, last_name=employee.last_name, is_active=True)
                text = f'Account {user.username} created and linked.'
            elif mode == MODE_LINK:
                user = data['existing_user']
                text = f'Account {user.username} linked.'
            if user:
                employee.user = user
                employee.save(update_fields=['user'])
                UserAuditLog.objects.create(user=self.acting_user, action='create' if mode == MODE_CREATE else 'update',
                                            content_type='accounts.CustomUser', object_id=user.pk,
                                            description=f'Employee page: {text} (employee {employee.employee_id})')
        return text
