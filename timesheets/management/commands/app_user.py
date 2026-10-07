"""
Give an employee a login for the mobile app (and the web system): creates the user if it does not exist and links it to the
employee's HR record, which is what the app needs to open ("No employee record may be linked to this account yet").

    python manage.py app_user --list                       employees and whether they already have a login
    python manage.py app_user SAMER --employee EMP011      create the login "SAMER" for employee EMP011 (a password is generated)
    python manage.py app_user SAMER --employee "سامر"     the employee can be found by part of the name when it is unique
    python manage.py app_user SAMER --employee EMP011 --role admin --password "..."   choose the role / the password

Roles: site_engineer (default; can record the day-labor workers of his own projects), project_manager, engineering_manager,
general_manager, accountant, admin. An existing user is only linked (and gets the new password when --password is given).
"""
import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.models import CustomUser
from timesheets.models import Employee


class Command(BaseCommand):
    help = "Create / link a login for an employee so he can use the mobile app"

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', help='Username to log in with')
        parser.add_argument('--employee', help='Employee ID (EMP011) or a part of the name')
        parser.add_argument('--role', default='site_engineer', choices=[r for r, _ in CustomUser.USER_ROLES])
        parser.add_argument('--password', help='Password (generated and printed when left out)')
        parser.add_argument('--list', action='store_true', help='List the employees and their logins')

    def handle(self, *args, **opts):
        if opts['list']:
            for e in Employee.objects.select_related('user').order_by('employee_id'):
                login = f"{e.user.username} ({e.user.role})" if e.user_id else '-- no login --'
                self.stdout.write(f"{e.employee_id:8} {e.full_name:35} {e.employment_status:10} {login}")
            return

        username, query = opts['username'], (opts['employee'] or '').strip()
        if not username or not query:
            raise CommandError('Give the username and --employee (or use --list).')

        matches = list(Employee.objects.filter(employee_id__iexact=query))
        if not matches:
            matches = list(Employee.objects.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query)))
            parts = query.split()
            if not matches and len(parts) > 1:
                matches = [e for e in Employee.objects.all() if all(p in e.full_name for p in parts)]
        if not matches:
            raise CommandError(f'No employee matches "{query}". Use --list to see them.')
        if len(matches) > 1:
            names = '; '.join(f'{e.employee_id} {e.full_name}' for e in matches)
            raise CommandError(f'More than one employee matches "{query}": {names}. Use the employee ID.')
        employee = matches[0]

        user = CustomUser.objects.filter(username=username).first()
        if employee.user_id and (user is None or employee.user_id != user.id):
            raise CommandError(f'{employee.full_name} is already linked to the user "{employee.user.username}".')
        if user is not None:
            other = Employee.objects.filter(user=user).exclude(pk=employee.pk).first()
            if other:
                raise CommandError(f'The user "{username}" is already linked to {other.full_name} ({other.employee_id}).')
        generated = None
        if user is None:
            password = opts['password'] or secrets.token_urlsafe(9)
            generated = None if opts['password'] else password
            user = CustomUser.objects.create_user(
                username=username, password=password, role=opts['role'], email=employee.email or '',
                first_name=employee.first_name, last_name=employee.last_name,
            )
            self.stdout.write(self.style.SUCCESS(f'Created the user "{username}" ({user.role}).'))
        else:
            if opts['password']:
                user.set_password(opts['password'])
                user.save(update_fields=['password'])
                self.stdout.write('The password was changed.')
            self.stdout.write(f'The user "{username}" already exists ({user.role}); only linking it.')

        employee.user = user
        employee.save(update_fields=['user'])

        self.stdout.write(self.style.SUCCESS(f'Linked to {employee.full_name} ({employee.employee_id}).'))
        self.stdout.write(f'Log in to the app with username: {username}')
        if generated:
            self.stdout.write(f'Password: {generated}   (write it down; it is not stored anywhere readable)')
