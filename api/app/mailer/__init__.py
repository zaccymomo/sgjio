"""Sending email (SCRUM-74).

Three backends, chosen with EMAIL_BACKEND:

- smtp     send through SMTP_HOST:SMTP_PORT. Locally that is Mailpit from docker compose,
           which catches everything, so no real email goes out while testing. For the demo
           environment, point it at a real provider's SMTP details in the server's .env.
- console  print the email to the API's terminal. Handy without Docker.
- memory   keep emails in `outbox`. Used by the tests.

Credentials always come from environment variables, never from the repository.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as _MimeMessage

from app.config import get_settings

logger = logging.getLogger("sgjio.mailer")


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


# Emails "sent" with the memory backend, newest last.
outbox: list[EmailMessage] = []


def send_email(message: EmailMessage) -> None:
    settings = get_settings()
    if settings.email_backend == "memory":
        outbox.append(message)
    elif settings.email_backend == "console":
        logger.warning(
            "\n--- Email (console backend) ---\nTo: %s\nSubject: %s\n\n%s\n---",
            message.to,
            message.subject,
            message.text,
        )
    else:
        _send_smtp(message)


def _send_smtp(message: EmailMessage) -> None:
    settings = get_settings()
    mime = _MimeMessage()
    mime["From"] = settings.email_from
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(mime)
