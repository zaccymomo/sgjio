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

    Both stories require the email to say how long the link is valid (AC3): `minutes`,
    which is Identity's RESET_TOKEN_MINUTES (15 on the microservices branch, 5 in the
    monolith), carried in the event.
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


def google_account_email(*, to: str, name: str, link: str) -> EmailMessage:
    """Sent instead of a reset link to an account created with Google (SCRUM-92), which has
    no password to reset."""
    subject = "How you sign in to SGJio"
    text = (
        f"Hi {name},\n\n"
        "We received a request to reset your SGJio password. Your account doesn't have a "
        "password: you sign in with Google.\n\n"
        f'On the sign-in page, select "Continue with Google" and use {to}:\n\n{link}\n\n'
        "If you did not ask for this, you can ignore this email.\n\nThe SGJio team"
    )
    body = f"""\
<p style="margin:0 0 12px;">Hi {escape(name)},</p>
<p style="margin:0 0 16px;">
  We received a request to reset your SGJio password. Your account doesn't have a
  password: you sign in with Google.
</p>
<p style="margin:0 0 16px;">
  On the sign-in page, select <strong>Continue with Google</strong> and use
  <strong>{escape(to)}</strong>.
</p>
{_button(link, "Go to sign in")}
<p style="margin:0;color:{_MUTED};font-size:12px;">
  If you did not ask for this, you can ignore this email.
</p>
"""
    return EmailMessage(
        to=to, subject=subject, text=text, html=_layout("You sign in with Google", body)
    )


def _duration(hours: int) -> str:
    """72 -> "3 days", 12 -> "12 hours"."""
    if hours % 24 == 0:
        days = hours // 24
        return f"{days} day{'' if days == 1 else 's'}"
    return f"{hours} hour{'' if hours == 1 else 's'}"


def _button(link: str, label: str) -> str:
    return f"""\
<p style="margin:0 0 16px;">
  <a href="{escape(link)}"
     style="display:inline-block;background:{_INK};color:#FFFFFF;text-decoration:none;
            padding:10px 18px;border-radius:4px;font-weight:600;">{escape(label)}</a>
</p>"""


def admin_invite_email(
    *, to: str, name: str, inviter: str | None, link: str, hours: int, restored: bool = False
) -> EmailMessage:
    """An invitation to the admin portal, or access given back, from SCRUM-81.

    `inviter` is the administrator who sent it; empty when the person asked for a new link
    themselves.
    """
    valid = _duration(hours)
    if restored:
        subject = "Your SGJio admin access is back"
        heading = "Your admin access is back"
        who = inviter or "An administrator"
        opening = f"{who} has given you access to the SGJio admin portal again."
        label = "Choose a password"
    elif inviter:
        subject = f"{inviter} invited you to the SGJio admin portal"
        heading = "You're invited to SGJio admin"
        opening = f"{inviter} has invited you to help run SGJio's lessons in the admin portal."
        label = "Set up your account"
    else:
        subject = "Set up your SGJio admin account"
        heading = "Set up your admin account"
        opening = "Here is a new link to set up your SGJio admin account."
        label = "Set up your account"

    text = (
        f"Hi {name},\n\n{opening}\n"
        f"Open this link to choose a password. It is valid for {valid} and can be used once:\n\n"
        f"{link}\n\n"
        f"You will sign in with this email address: {to}\n\n"
        "If you were not expecting this, you can ignore this email.\n\nThe SGJio team"
    )
    body = f"""\
<p style="margin:0 0 12px;">Hi {escape(name)},</p>
<p style="margin:0 0 16px;">{escape(opening)}</p>
{_button(link, label)}
<p style="margin:0 0 16px;color:{_MUTED};">
  This link is valid for <strong>{valid}</strong> and can be used once. You will sign in
  with <strong>{escape(to)}</strong>.
</p>
<p style="margin:0;color:{_MUTED};font-size:12px;">
  If you were not expecting this, you can ignore this email.
</p>
"""
    return EmailMessage(to=to, subject=subject, text=text, html=_layout(heading, body))


def admin_removed_email(*, to: str, name: str, remover: str) -> EmailMessage:
    """Tells a removed administrator who removed them (SCRUM-81), so it never happens silently."""
    subject = "Your SGJio admin access has been removed"
    text = (
        f"Hi {name},\n\n"
        f"{remover} has removed your access to the SGJio admin portal. You have been signed "
        "out and can no longer sign in.\n\n"
        f"If you think this is a mistake, contact {remover} or another administrator. "
        "They can restore your access at any time.\n\nThe SGJio team"
    )
    body = f"""\
<p style="margin:0 0 12px;">Hi {escape(name)},</p>
<p style="margin:0 0 16px;">
  {escape(remover)} has removed your access to the SGJio admin portal. You have been signed
  out and can no longer sign in.
</p>
<p style="margin:0;color:{_MUTED};">
  If you think this is a mistake, contact {escape(remover)} or another administrator. They
  can restore your access at any time.
</p>
"""
    return EmailMessage(
        to=to, subject=subject, text=text, html=_layout("Your admin access was removed", body)
    )
