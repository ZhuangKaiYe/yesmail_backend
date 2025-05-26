from email.message import EmailMessage
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import imaplib
import os
import smtplib
from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.files.base import ContentFile
from mail.utils import decrypt, encrypt, send_smtp_email
from .serializers import RegisterSerializer, LoginSerializer, EmailSerializer
from django.contrib.auth import get_user_model
from .models import Attachment, BoundEmailAccount, Email
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from django.utils.timezone import now
User = get_user_model()


class RegisterUserView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User registered successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginUserView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Email.objects.filter(recipients=request.user)

        sender = request.query_params.get('sender')
        subject = request.query_params.get('subject')

        if sender:
            qs = qs.filter(from_user__username__icontains=sender)
        if subject:
            qs = qs.filter(subject__icontains=subject)

        qs = qs.order_by('-sent_at')
        serializer = EmailSerializer(qs, many=True)
        return Response(serializer.data)


class ListSentEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Email.objects.filter(from_user=request.user)

        recipient = request.query_params.get('recipient')
        subject = request.query_params.get('subject')

        if recipient:
            qs = qs.filter(recipients__username__icontains=recipient)
        if subject:
            qs = qs.filter(subject__icontains=subject)

        qs = qs.order_by('-sent_at')
        serializer = EmailSerializer(qs.distinct(), many=True)
        return Response(serializer.data)


# class EmailCreateView(APIView):
#     permission_classes = [permissions.IsAuthenticated]

#     def post(self, request):
#         data = request.data.copy()
#         data['sender'] = request.user.id
#         serializer = EmailSerializer(data=data)
#         if serializer.is_valid():
#             serializer.save(from_user=request.user)
#             return Response({"message": "Email sent successfully"}, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UploadAttachmentView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, email_id):
        try:
            email = Email.objects.get(id=email_id, from_user=request.user)
        except Email.DoesNotExist:
            return Response({"error": "Email not found or permission denied"}, status=404)

        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided"}, status=400)

        attachment = Attachment.objects.create(
            email=email,
            file=file,
            filename=file.name
        )


class DownloadAttachmentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, attachment_id):
        try:
            # 查询附件对象
            attachment = Attachment.objects.select_related(
                "email__from_user").get(pk=attachment_id)
        except Attachment.DoesNotExist:
            return Response(
                {"detail": f"Attachment with id {attachment_id} not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        if (
            request.user != attachment.email.from_user
            and not attachment.email.recipients.filter(id=request.user.id).exists()
        ):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        file_path = attachment.file.path
        if not os.path.exists(file_path):
            return Response(
                {"detail": "File not found on server."},
                status=status.HTTP_410_GONE
            )

        try:
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=attachment.filename)
        except Exception as e:
            return Response(
                {"detail": f"Unexpected error while opening file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


User = get_user_model()


class SendEmailByPosifixView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        subject = data.get('subject')
        body = data.get('body')
        recipients = data.get('recipients', [])
        attachment_ids = data.get('attachments', [])

        if not recipients:
            return Response({'error': '收件人不能为空'}, status=400)

        internal_users = User.objects.filter(email__in=recipients)
        internal_emails = set(u.email for u in internal_users)
        external_emails = set(recipients) - internal_emails

        attachments = []
        for att_id in attachment_ids:
            try:
                att = Attachment.objects.get(pk=att_id)
                attachments.append((att.file.path, att.filename))
            except Attachment.DoesNotExist:
                continue

        if internal_users.exists():
            email_obj = Email.objects.create(
                from_user=request.user,
                subject=subject,
                body=body,
                is_internal=True
            )
            email_obj.recipients.set(internal_users)
            for att_path, filename in attachments:
                Attachment.objects.create(
                    email=email_obj, file=att_path, filename=filename)

        if external_emails:
            try:
                send_smtp_email(
                    from_user_email=request.user.email,
                    to_external=", ".join(external_emails),
                    subject=subject,
                    body=body,
                    attachments=attachments,
                )
            except Exception as e:
                return Response({'error': f'外部邮件发送失败: {str(e)}'}, status=500)

        return Response({'message': '邮件发送成功'}, status=200)


class BindExternalEmailAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data

        email = data.get("email")
        password = data.get("password")  # 授权码或邮箱密码
        smtp_server = data.get("smtp_server")
        smtp_port = int(data.get("smtp_port"))
        imap_server = data.get("imap_server")
        imap_port = int(data.get("imap_port"))
        use_ssl = data.get("use_ssl", True)

        try:
            if use_ssl:
                imap = imaplib.IMAP4_SSL(imap_server, imap_port)
            else:
                imap = imaplib.IMAP4(imap_server, imap_port)
            imap.login(email, password)
            imap.logout()
        except Exception as e:
            return Response({"error": f"IMAP 登录失败: {str(e)}"}, status=400)

        try:
            if use_ssl and smtp_port == 465:
                smtp = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                smtp = smtplib.SMTP(smtp_server, smtp_port)
                smtp.starttls()
            smtp.login(email, password)
            smtp.quit()
        except Exception as e:
            return Response({"error": f"SMTP 登录失败: {str(e)}"}, status=400)

        BoundEmailAccount.objects.update_or_create(
            user=user,
            email_address=email,
            defaults={
                "smtp_server": smtp_server,
                "smtp_port": smtp_port,
                "imap_server": imap_server,
                "imap_port": imap_port,
                "use_ssl": use_ssl,
                "password_encrypted": encrypt(password)
            }
        )

        return Response({"message": "绑定成功"})


class FetchExternalInboxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        limit = int(request.query_params.get("limit", 10))
        offset = int(request.query_params.get("offset", 0))

        try:
            bound = BoundEmailAccount.objects.get(user=user)
        except BoundEmailAccount.DoesNotExist:
            return Response({"error": "未绑定邮箱"}, status=400)

        password = decrypt(bound.password_encrypted)

        try:
            if bound.use_ssl:
                imap = imaplib.IMAP4_SSL(bound.imap_server, bound.imap_port)
            else:
                imap = imaplib.IMAP4(bound.imap_server, bound.imap_port)

            imap.login(bound.email_address, password)
            imap.select("INBOX")

            result, data = imap.search(None, "ALL")
            mail_ids = data[0].split()

            fetched_uids = set(Email.objects.filter(
                external_account=bound).values_list("external_uid", flat=True))

            emails = []
            for mail_id in reversed(mail_ids):
                uid = mail_id.decode()
                if uid in fetched_uids:
                    continue  # 跳过已保存的邮件

                result, msg_data = imap.fetch(mail_id, "(RFC822)")
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject, _ = decode_header(msg["Subject"])[0]
                subject = subject.decode() if isinstance(subject, bytes) else subject
                from_ = msg.get("From")
                date_ = parsedate_to_datetime(msg.get("Date"))
                is_read = "\\Seen" in imap.fetch(
                    mail_id, '(FLAGS)')[1][0].decode()

                body = ""
                attachments = []

                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = part.get("Content-Disposition")
                        if content_type == "text/plain" and not content_disposition:
                            body += part.get_payload(
                                decode=True).decode(errors="ignore")
                        elif "attachment" in str(content_disposition):
                            filename = part.get_filename()
                            if filename:
                                filename = decode_header(filename)[0][0]
                                filename = filename.decode() if isinstance(filename, bytes) else filename
                                content = part.get_payload(decode=True)

                                email_obj = Email.objects.create(
                                    from_user=user,
                                    to_external=from_,
                                    subject=subject,
                                    body=body,
                                    is_internal=False,
                                    is_read=is_read,
                                    sent_at=date_,
                                    external_uid=uid,
                                    external_account=bound
                                )
                                att = Attachment(
                                    email=email_obj,
                                    filename=filename
                                )
                                att.file.save(filename, ContentFile(content))
                                att.save()
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")

                    email_obj = Email.objects.create(
                        from_user=user,
                        to_external=from_,
                        subject=subject,
                        body=body,
                        is_internal=False,
                        is_read=is_read,
                        sent_at=date_,
                        external_uid=uid,
                        external_account=bound
                    )

            imap.logout()

            qs = Email.objects.filter(
                from_user=user, is_internal=False).order_by('-sent_at')
            limit = int(request.query_params.get("limit", 10))
            offset = int(request.query_params.get("offset", 0))
            emails = qs[offset:offset+limit]
            serializer = EmailSerializer(emails, many=True)
            return Response(serializer.data)

        except Exception as e:
            return Response({"error": f"IMAP 拉取失败: {str(e)}"}, status=500)


class GetEmailDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            email = Email.objects.prefetch_related("attachments").get(pk=pk)
        except Email.DoesNotExist:
            return Response({"error": "邮件不存在"}, status=404)

        if email.from_user != request.user and not email.recipients.filter(id=request.user.id).exists():
            return Response({"error": "无权限查看此邮件"}, status=403)

        serializer = EmailSerializer(email)
        return Response(serializer.data)


class SendEmailWithBoundAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data

        to_emails = data.get("to")
        subject = data.get("subject")
        body = data.get("body")
        attachments_ids = data.get("attachments", [])

        if not to_emails:
            return Response({"error": "收件人不能为空"}, status=400)
        if not subject:
            return Response({"error": "主题不能为空"}, status=400)

        try:
            bound = BoundEmailAccount.objects.get(user=user)
        except BoundEmailAccount.DoesNotExist:
            return Response({"error": "请先绑定邮箱账号"}, status=400)

        password = decrypt(bound.password_encrypted)

        msg = EmailMessage()
        msg["From"] = bound.email_address
        msg["To"] = ", ".join(to_emails) if isinstance(
            to_emails, list) else to_emails
        msg["Subject"] = subject
        msg.set_content(body or "")

        attachment = []

        for att_id in attachments_ids:
            try:
                att = Attachment.objects.get(id=att_id, email__from_user=user)
                with open(att.file.path, "rb") as f:
                    file_data = f.read()
                    msg.add_attachment(
                        file_data, maintype="application", subtype="octet-stream", filename=att.filename)
                attachment.append(att)
            except Exception:
                continue

        try:
            if bound.use_ssl and bound.smtp_port == 465:
                server = smtplib.SMTP_SSL(bound.smtp_server, bound.smtp_port)
            else:
                server = smtplib.SMTP(bound.smtp_server, bound.smtp_port)
                server.starttls()

            server.login(bound.email_address, password)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            return Response({"error": f"邮件发送失败: {str(e)}"}, status=500)

        email_obj = Email.objects.create(
            from_user=user,
            subject=subject,
            body=body or "",
            is_internal=False,
            sent_at=now(),
            to_external=", ".join(to_emails) if isinstance(
                to_emails, list) else to_emails
        )

        for att in attachment:
            Attachment.objects.create(
                email=email_obj,
                file=att.file,
                filename=att.filename
            )

        return Response({"message": "邮件发送成功"})
