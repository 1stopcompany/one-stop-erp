"""
One-time migration: copy every file already on local disk (MEDIA_ROOT) up to Dropbox, at the exact same
relative path it has locally -- the same relative path every FileField in the database already stores.

Run this BEFORE setting DROPBOX_APP_KEY/DROPBOX_APP_SECRET/DROPBOX_OAUTH2_REFRESH_TOKEN in .env (which is
what switches new uploads over to Dropbox -- see config/settings.py). Skipping this step means every
insurance certificate, tender document, drawing and report photo uploaded before the switch becomes
unreachable the moment it goes live, because Dropbox has nothing at the path the database points to.

Safe to re-run: a file that's already on Dropbox at its target path is left alone and skipped, so an
interrupted run can just be started again.

Usage:
    python manage.py migrate_media_to_dropbox              # upload what's missing
    python manage.py migrate_media_to_dropbox --dry-run     # list what would be uploaded, upload nothing
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Copy every file already on local disk (MEDIA_ROOT) up to Dropbox, before switching new uploads over to it."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List what would be uploaded without uploading anything")

    def handle(self, *args, **options):
        media_root = settings.MEDIA_ROOT
        if not media_root.is_dir():
            self.stdout.write("No media directory yet -- nothing to migrate.")
            return

        if not settings.DROPBOX_APP_KEY:
            raise CommandError(
                "DROPBOX_APP_KEY (and DROPBOX_APP_SECRET / DROPBOX_OAUTH2_REFRESH_TOKEN) aren't set yet. "
                "Set them in .env first -- this command uploads TO the Dropbox they identify."
            )

        try:
            from storages.backends.dropbox import DropboxStorage
        except ImportError:
            raise CommandError("django-storages and dropbox aren't installed -- pip install -r requirements.txt")

        try:
            storage = DropboxStorage()
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc))

        local_files = sorted(p for p in media_root.rglob("*") if p.is_file())
        self.stdout.write(f"Found {len(local_files)} file(s) under {media_root}.")

        uploaded = skipped = failed = 0
        for path in local_files:
            rel_name = path.relative_to(media_root).as_posix()
            try:
                if storage.exists(rel_name):
                    skipped += 1
                    continue
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f"Couldn't check {rel_name} on Dropbox ({exc}) -- skipping."))
                failed += 1
                continue

            if options["dry_run"]:
                self.stdout.write(f"Would upload: {rel_name}")
                uploaded += 1
                continue

            try:
                with open(path, "rb") as fh:
                    storage.save(rel_name, File(fh, name=rel_name))
                uploaded += 1
                self.stdout.write(f"Uploaded: {rel_name}")
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Failed to upload {rel_name}: {exc}"))
                failed += 1

        verb = "Would upload" if options["dry_run"] else "Uploaded"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {uploaded}, already on Dropbox {skipped}, failed {failed}."
        ))
        if failed:
            self.stderr.write(self.style.WARNING("Re-run the command to retry the failed ones -- already-uploaded files are skipped."))
