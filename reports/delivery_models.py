"""Record of what happened when a submitted daily report was sent out (e-mail notification + PDF copy in the project's Dropbox folder)."""
from django.db import models


class ReportDelivery(models.Model):
    report = models.ForeignKey('reports.DailyReport', on_delete=models.CASCADE, related_name='deliveries')
    created_at = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=200, blank=True)

    email_to = models.TextField(blank=True, help_text='Addresses the notification was sent to')
    email_ok = models.BooleanField(null=True, help_text='True sent, False failed, empty = not attempted')
    email_error = models.TextField(blank=True)

    dropbox_path = models.CharField(max_length=600, blank=True)
    dropbox_ok = models.BooleanField(null=True, help_text='True saved, False failed, empty = project has no Dropbox folder')
    dropbox_error = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.report_id} delivery {self.created_at:%Y-%m-%d %H:%M}'

    @property
    def all_ok(self):
        return self.email_ok is not False and self.dropbox_ok is not False
