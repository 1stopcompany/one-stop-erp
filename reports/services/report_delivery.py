"""
What happens when a site engineer submits a daily report: the project's manager and the engineering manager(s) (plus any extra
addresses set on the project) get an e-mail with the report as a PDF attachment, and the same PDF is saved in the project's Dropbox
folder (Project.report_dropbox_folder: a folder path in the company Dropbox, or a shared link to a folder of that account).

It runs in the background so the engineer is not kept waiting; each part (e-mail, Dropbox) succeeds or fails on its own and the
outcome is stored in a ReportDelivery row, shown on the report page with a Retry button. A resubmitted report overwrites the same
file name, so the folder never fills with copies of one day.
"""
import logging
import re
import threading

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import connections
from django.urls import reverse

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    pass


def pdf_filename(report):
    symbol = re.sub(r'[^A-Za-z0-9_-]+', '-', report.project.project_symbol or 'project')
    return f'{symbol}_{report.report_date:%Y-%m-%d}_Daily_Report.pdf'


def recipients(report):
    """Project manager, every active engineering manager, and the project's extra addresses (no duplicates)."""
    from accounts.models import CustomUser
    found = []
    manager = report.project.manager
    if manager and manager.is_active and manager.email:
        found.append(manager.email)
    found += list(CustomUser.objects.filter(role='engineering_manager', is_active=True).exclude(email='').values_list('email', flat=True))
    found += [e.strip() for e in re.split(r'[,;\s]+', report.project.report_notify_emails or '') if e.strip()]
    seen, unique = set(), []
    for email in found:
        if email.lower() not in seen:
            seen.add(email.lower())
            unique.append(email)
    return unique


# ------------------------------------------------------------------ Dropbox
def dropbox_client():
    import dropbox
    if not (settings.DROPBOX_APP_KEY and settings.DROPBOX_APP_SECRET and settings.DROPBOX_OAUTH2_REFRESH_TOKEN):
        raise DeliveryError('Dropbox is not set up on this server (DROPBOX_APP_KEY / DROPBOX_APP_SECRET / DROPBOX_OAUTH2_REFRESH_TOKEN in .env).')
    return dropbox.Dropbox(oauth2_refresh_token=settings.DROPBOX_OAUTH2_REFRESH_TOKEN, app_key=settings.DROPBOX_APP_KEY, app_secret=settings.DROPBOX_APP_SECRET)


def resolve_folder(client, value):
    """The folder as a Dropbox path: a typed path is used as it is; a shared link is looked up in the company account."""
    value = (value or '').strip()
    if not value.lower().startswith('http'):
        return '/' + value.strip('/')
    # The address bar of Dropbox's own web page (https://www.dropbox.com/home/<folder path>) carries the path itself
    from urllib.parse import unquote, urlparse
    parsed = urlparse(value)
    if parsed.netloc.lower().endswith('dropbox.com') and (parsed.path == '/home' or parsed.path.startswith('/home/')):
        return '/' + unquote(parsed.path[len('/home'):]).strip('/')
    try:
        meta = client.sharing_get_shared_link_metadata(value)
    except Exception as error:
        raise DeliveryError(f'Dropbox could not open the folder link: {error}')
    path = getattr(meta, 'path_lower', None)
    if not path and getattr(meta, 'id', None):
        try:
            path = client.files_get_metadata(meta.id).path_display
        except Exception:
            path = None
    if not path:
        raise DeliveryError('The folder behind this link is not inside the company Dropbox account. Share the folder with the company account '
                            '(edit access) and add it to its Dropbox, or type the folder path instead of the link.')
    return path


def save_to_dropbox(report, pdf, filename, client=None):
    import dropbox
    client = client or dropbox_client()
    folder = resolve_folder(client, report.project.report_dropbox_folder).rstrip('/')
    path = f'{folder}/{filename}'
    try:
        client.files_upload(pdf, path, mode=dropbox.files.WriteMode.overwrite)
    except Exception as error:
        raise DeliveryError(f'Dropbox refused the upload to {path}: {error}')
    return path


def photos_folder_setting(project):
    """The folder (path or link) the report photos go to: the project's own photos folder, else 'Photos' inside the reports folder."""
    if (project.photos_dropbox_folder or '').strip():
        return project.photos_dropbox_folder.strip(), False
    if (project.report_dropbox_folder or '').strip():
        return project.report_dropbox_folder.strip(), True     # True = add a "Photos" subfolder
    return '', False


def photo_filename(report, number, attachment):
    import os
    symbol = re.sub(r'[^A-Za-z0-9_-]+', '-', report.project.project_symbol or 'project')
    ext = os.path.splitext(attachment.file.name)[1].lower() or '.jpg'
    label = re.sub(r'[^\w]+', '-', attachment.description or '', flags=re.UNICODE).strip('-')[:40]
    return f'{symbol}_{report.report_date:%Y-%m-%d}_{number:02d}' + (f'_{label}' if label else '') + ext


def copy_photos(report, delivery, client):
    """Copy the report's photo attachments (not videos, documents or others) to <photos folder>/<YYYY-MM-DD>/ . Records the outcome."""
    import dropbox
    from reports.models import ReportAttachment
    setting, add_subfolder = photos_folder_setting(report.project)
    if not setting:
        return
    photos = list(ReportAttachment.objects.filter(report_type='daily', report_id=report.pk, attachment_type='photo').order_by('order', 'created_at', 'pk'))
    delivery.photos_total = len(photos)
    if not photos:
        return
    try:
        folder = resolve_folder(client, setting).rstrip('/') + ('/Photos' if add_subfolder else '') + f'/{report.report_date:%Y-%m-%d}'
    except Exception as error:
        delivery.photos_error = str(error)
        return
    problems = []
    for number, photo in enumerate(photos, start=1):
        name = photo_filename(report, number, photo)
        try:
            with photo.file.open('rb') as handle:
                data = handle.read()
            client.files_upload(data, f'{folder}/{name}', mode=dropbox.files.WriteMode.overwrite)
            delivery.photos_copied += 1
        except Exception as error:
            logger.exception('Photo %s of report %s could not be copied to Dropbox', photo.pk, report.pk)
            problems.append(f'{name}: {error}')
    delivery.photos_error = '; '.join(problems)[:1500]


# ------------------------------------------------------------------ e-mail
def send_notification(report, pdf, filename, to):
    if settings.EMAIL_BACKEND.endswith('dummy.EmailBackend'):
        raise DeliveryError('E-mail is not set up on this server (EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD in .env).')
    link = f"{settings.SITE_URL}{reverse('reports:daily_report_detail', args=[report.pk])}"
    engineer = report.site_engineer.get_full_name() or report.site_engineer.username
    subject = f'[{report.project.project_symbol}] Daily report {report.report_date:%d/%m/%Y} submitted'
    body = (f'The daily report of {report.project.name} ({report.project.project_symbol}) for {report.report_date:%d/%m/%Y} '
            f'was submitted by {engineer}.\n\nReport number: {report.report_number}\n\n'
            f'Open it: {link}\n\nThe report is attached as a PDF.\n')
    message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, to)
    message.attach(filename, pdf, 'application/pdf')
    message.send(fail_silently=False)


# ------------------------------------------------------------------ the whole delivery
def deliver(report_id, dropbox_factory=None):
    """Send the notification and save the PDF for one submitted report. Returns the ReportDelivery row (never raises)."""
    from reports.delivery_models import ReportDelivery
    from reports.models import DailyReport
    from reports.utils import generate_daily_report_pdf

    report = DailyReport.all_objects.select_related('project', 'project__manager', 'site_engineer').get(pk=report_id)
    delivery = ReportDelivery.objects.create(report=report, filename=pdf_filename(report))
    try:
        return _run_delivery(report, delivery, dropbox_factory, generate_daily_report_pdf)
    except Exception as error:   # whatever goes wrong, the row must not stay "in progress" for ever
        logger.exception('Daily report delivery crashed for %s', report_id)
        delivery.email_error = delivery.email_error or f'Delivery failed: {error}'
        delivery.email_ok = False if delivery.email_ok is None else delivery.email_ok
        delivery.finished = True
        delivery.save()
        return delivery


def _run_delivery(report, delivery, dropbox_factory, generate_daily_report_pdf):
    report_id = report.pk
    pdf, pdf_error = None, ''
    try:
        pdf = generate_daily_report_pdf(report)
    except Exception as error:
        logger.exception('Daily report PDF failed for %s', report_id)
        pdf_error = f'The PDF could not be generated: {error}'

    to = recipients(report)
    delivery.email_to = ', '.join(to)
    if pdf is None:
        delivery.email_ok, delivery.email_error = False, pdf_error
    elif to:
        try:
            send_notification(report, pdf, delivery.filename, to)
            delivery.email_ok = True
        except Exception as error:
            logger.exception('Daily report e-mail failed for %s', report_id)
            delivery.email_ok, delivery.email_error = False, str(error)
    else:
        delivery.email_ok = False
        delivery.email_error = 'No e-mail address to send to (set e-mails on the managers or on the project).'

    client = None

    def get_client():
        nonlocal client
        if client is None:
            client = dropbox_factory() if dropbox_factory else dropbox_client()
        return client

    if pdf is None and (report.project.report_dropbox_folder or '').strip():
        delivery.dropbox_ok, delivery.dropbox_error = False, pdf_error
    elif (report.project.report_dropbox_folder or '').strip():
        try:
            delivery.dropbox_path = save_to_dropbox(report, pdf, delivery.filename, client=get_client())
            delivery.dropbox_ok = True
        except Exception as error:
            logger.exception('Daily report Dropbox upload failed for %s', report_id)
            delivery.dropbox_ok, delivery.dropbox_error = False, str(error)
    if photos_folder_setting(report.project)[0]:
        try:
            copy_photos(report, delivery, get_client())
        except Exception as error:
            logger.exception('Daily report photo copy failed for %s', report_id)
            delivery.photos_error = str(error)
    delivery.finished = True
    delivery.save()
    return delivery


def deliver_in_background(report_id):
    """Start deliver() on its own thread (settings.REPORT_DELIVERY_IN_BACKGROUND = False runs it right away, as tests do)."""
    if not getattr(settings, 'REPORT_DELIVERY_IN_BACKGROUND', True):
        return deliver(report_id)

    def run():
        try:
            deliver(report_id)
        except Exception:
            logger.exception('Daily report delivery crashed for %s', report_id)
        finally:
            connections.close_all()

    threading.Thread(target=run, name=f'report-delivery-{report_id}', daemon=True).start()
    return None
