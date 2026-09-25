"""Email templates. Plain HTML with inline styles, since email clients ignore stylesheets."""

from html import escape

from app.mailer import EmailMessage

# Colours from the SGJIO Figma file.
_BRAND = "#F43F5E"
_INK = "#111827"
_MUTED = "#4B5563"
_LINE = "#E5E7EB"


def _layout(heading: str, body_html: str) -> str:
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#F9FAFB;font-family:Inter,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="max-width:480px;margin:0 auto;background:#FFFFFF;border:1px solid {_LINE};
                  border-radius:8px;">
      <tr>
        <td style="padding:20px 24px;border-bottom:3px solid {_BRAND};">
          <span style="font-size:18px;font-weight:700;color:{_INK};">SGJio</span>
        </td>
      </tr>
      <tr>
        <td style="padding:24px;color:{_INK};font-size:14px;line-height:1.5;">
          <h1 style="margin:0 0 12px;font-size:18px;">{escape(heading)}</h1>
          {body_html}
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def password_reset_email(
    *, to: str, name: str, link: str, minutes: int, for_admin: bool
) -> EmailMessage:
    """The reset email for SCRUM-63 (main app) and SCRUM-69 (admin portal).

    Both stories require the email to say the link is valid for 5 minutes (AC3).
    """
    where = "the SGJio admin portal" if for_admin else "SGJio"
    subject = "Reset your SGJio admin password" if for_admin else "Reset your SGJio password"
    text = (
        f"Hi {name},\n\n"
        f"We received a request to reset your password for {where}.\n"
        f"Open this link to choose a new password. It is valid for {minutes} minutes "
        f"and can be used once:\n\n{link}\n\n"
        "If you did not ask for this, you can ignore this email. Your password has not "
        "changed.\n\nThe SGJio team"
    )
    body = f"""\
<p style="margin:0 0 12px;">Hi {escape(name)},</p>
<p style="margin:0 0 16px;">We received a request to reset your password for {escape(where)}.</p>
<p style="margin:0 0 16px;">
  <a href="{escape(link)}"
     style="display:inline-block;background:{_INK};color:#FFFFFF;text-decoration:none;
            padding:10px 18px;border-radius:4px;font-weight:600;">Choose a new password</a>
</p>
<p style="margin:0 0 16px;color:{_MUTED};">
  This link is valid for <strong>{minutes} minutes</strong> and can be used once.
</p>
<p style="margin:0;color:{_MUTED};font-size:12px;">
  If you did not ask for this, you can ignore this email. Your password has not changed.
</p>
"""
    return EmailMessage(
        to=to, subject=subject, text=text, html=_layout("Reset your password", body)
    )
