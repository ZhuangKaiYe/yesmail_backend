import base64
from email.utils import formatdate, make_msgid
import smtplib
import mimetypes
from email.message import EmailMessage
import os
from django.conf import settings

def encrypt(password: str) -> str:
    return base64.b64encode(password.encode()).decode()

def decrypt(encrypted: str) -> str:
    return base64.b64decode(encrypted.encode()).decode()

def send_smtp_email(from_user_email, to_external, subject, body, attachments=None):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_user_email}"
        msg["To"] = to_external
        msg.set_content(body)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="ymail.com")

        if attachments:
            for file_path, filename in attachments:
                if not os.path.exists(file_path):
                    print(f"[warn] Attachment file not found: {file_path}")
                    continue

                mime_type, _ = mimetypes.guess_type(file_path)
                mime_type = mime_type or "application/octet-stream"
                maintype, subtype = mime_type.split("/", 1)

                with open(file_path, "rb") as f:
                    msg.add_attachment(
                        f.read(), maintype=maintype, subtype=subtype, filename=filename)

        # 使用系统本地 Postfix（默认监听 localhost:25）
        with smtplib.SMTP("localhost") as smtp:
            smtp.send_message(msg)
            print(f"[info] Mail sent to {to_external} via local Postfix")


        try:
            with smtplib.SMTP("localhost") as smtp:
                smtp.send_message(msg)
                print(f"[info] Mail sent to {to_external} via local Postfix")
        except Exception as e:
            raise RuntimeError(f"邮件发送失败：{e}")
