"""
Set a project's manager and / or site engineer by username -- the same on the local PC and on the server.

    python manage.py project_team TAB --manager ehab --site-engineer mahmoud.awawdeh            # preview only
    python manage.py project_team TAB --manager ehab --site-engineer mahmoud.awawdeh --apply

Only the two fields of the project are changed. The manager must be a project manager and the site engineer a site engineer (active
users). Reports already written keep their author; what changes is who sees and runs the project from now on (the project's own
page, new daily reports, the auto-created idle-day reports, the mobile app's project).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from projects.models import Project


class Command(BaseCommand):
    help = "Set a project's manager and / or site engineer."

    def add_arguments(self, parser):
        parser.add_argument('project', help='Project symbol, e.g. TAB')
        parser.add_argument('--manager', help='Username of the project manager (role: project_manager)')
        parser.add_argument('--site-engineer', dest='site_engineer', help='Username of the site engineer (role: site_engineer)')
        parser.add_argument('--apply', action='store_true', help='Write the change (without it: preview)')

    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=options['project']).first()
        if not project:
            raise CommandError(f"No project with the symbol {options['project']}.")
        if not options['manager'] and not options['site_engineer']:
            raise CommandError('Give --manager and / or --site-engineer.')
        User = get_user_model()
        changes = {}
        for option, field, role in (('manager', 'manager', 'project_manager'), ('site_engineer', 'site_engineer', 'site_engineer')):
            username = options[option]
            if not username:
                continue
            user = User.objects.filter(username=username, is_active=True).first()
            if not user:
                raise CommandError(f'No active user named {username} on this database; nothing was changed.')
            if user.role != role:
                raise CommandError(f'{username} is a {user.role}, not a {role}; nothing was changed.')
            changes[field] = user
        for field, user in changes.items():
            old = getattr(project, field)
            self.stdout.write(f"  {field}: {old.username if old else 'none'} -> {user.username} ({user.get_full_name() or user.username})")
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return
        for field, user in changes.items():
            setattr(project, field, user)
        project.save(update_fields=list(changes))
        self.stdout.write(self.style.SUCCESS(f'{project.project_symbol}: team updated.'))
