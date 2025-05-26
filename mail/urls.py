from django.conf.urls.static import static
from django.conf import settings
from django.urls import path
from .views import DownloadAttachmentView, UploadAttachmentView, BindExternalEmailAccountView, GetEmailDetailView, ListEmailView, SendEmailByPosifixView, FetchExternalInboxView, RegisterUserView, LoginUserView, SendEmailWithBoundAccountView, ListSentEmailView
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path('register/', RegisterUserView.as_view(), name='register'),
    path('login/', LoginUserView.as_view(), name='login'),

    path('emails/inbox/', ListEmailView.as_view(), name='email-inbox'),
    path('emails/sent/', ListSentEmailView.as_view(), name='email-sent'),
    path('emails/send/', SendEmailByPosifixView.as_view(), name='email-send'),
    path('emails/<int:email_id>/',
         GetEmailDetailView.as_view(), name='email-detail'),

    path('emails/<int:email_id>/attachments/upload/',
         UploadAttachmentView.as_view(), name='upload-attachment'),
    path('attachments/<int:attachment_id>/download/',
         DownloadAttachmentView.as_view(), name='attachment-download'),

    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('external-emails/bind/',
         BindExternalEmailAccountView.as_view(), name='bind-email'),
    path('external-emails/imap/fetch-inbox/',
         FetchExternalInboxView.as_view(), name='fetch-inbox'),
    path('external-emails/imap/send/', SendEmailWithBoundAccountView.as_view(),
         name='send-email-with-bound-account'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
