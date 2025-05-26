from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from datetime import datetime


# 用户模型
class User(AbstractUser):
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.email


# 邮件模型
class Email(models.Model):
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_emails')
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='received_emails')
    to_external = models.EmailField(null=True, blank=True)  # 外部收件人地址
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_internal = models.BooleanField(default=True)
    sent_at = models.DateTimeField("sent at", auto_now_add=True)
    is_read = models.BooleanField(default=False)

    external_uid = models.CharField(
        max_length=100, null=True, blank=True, db_index=True)
    external_account = models.ForeignKey(
        'BoundEmailAccount', null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.from_user} -> {self.to_user or self.to_external}'


def user_directory_path(instance, filename):
    user = instance.email.from_user
    today = datetime.today()
    return f'attachments/{user.username}/{today:%Y/%m/%d}/{filename}'


# 附件模型
class Attachment(models.Model):
    email = models.ForeignKey(
        Email, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to=user_directory_path)
    filename = models.CharField(max_length=255, default="")
    uploaded_at = models.DateTimeField("upload at", auto_now_add=True)

    def __str__(self):
        return self.filename


class BoundEmailAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_address = models.EmailField()
    smtp_server = models.CharField(max_length=255)
    smtp_port = models.IntegerField()
    imap_server = models.CharField(max_length=255)
    imap_port = models.IntegerField()
    use_ssl = models.BooleanField(default=True)
    password_encrypted = models.TextField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "email_address")
