# Decisions made during setup

Several Sprint 1 stories leave a value open for the team to decide. The setup tasks had to pick something to build on, so each one below is a **proposed default**. Every value is a single setting in `api/.env` (or one constant), so changing one after the team discusses it takes minutes.

| Open decision                           | Story              | Proposed default                                                                                                             | Where to change it                                                            |
| --------------------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Password rules                          | SCRUM-61           | At least 8 characters, at least one letter and one number, at most 128                                                       | `PASSWORD_MIN_LENGTH` and `password_rule_failures()` in `api/app/security.py` |
| Session length, main app                | SCRUM-62           | Signed out after **7 days without use**. Each visit extends it.                                                              | `APP_SESSION_DAYS`                                                            |
| Session length, admin portal            | SCRUM-68           | Signed out after **8 hours without use**                                                                                     | `ADMIN_SESSION_HOURS`                                                         |
| Failed attempts before blocking         | SCRUM-62, SCRUM-68 | **5 in a row** for the same email                                                                                            | `LOGIN_MAX_FAILURES`                                                          |
| Length of the block                     | SCRUM-62, SCRUM-68 | **15 minutes** from the last failure                                                                                         | `LOGIN_LOCKOUT_MINUTES`                                                       |
| Do admins and users share accounts?     | SCRUM-68           | **One accounts table** with a `role`, but **separate sessions**: signing in to one front end never signs you in to the other | `api/app/models.py`, `api/app/auth/`                                          |
| How are administrators created?         | SCRUM-68           | Seeded, or `python -m app.cli create-admin`                                                                                  | `api/app/cli.py`                                                              |
| Can a lesson be in more than one topic? | SCRUM-56           | **No, exactly one** (as the story assumes)                                                                                   | `Lesson.topic_id` in `api/app/models.py`                                      |
| Removed lessons: withdrawn or deleted?  | SCRUM-52           | **Withdrawn** (kept for users' history), as criterion 4 assumes                                                              | `LessonStatus.WITHDRAWN`                                                      |

Already fixed by the stories, and built as written:

- Reset links are valid for **5 minutes**, work **once**, and a new request cancels earlier links (SCRUM-63, SCRUM-69).
- Sign-in and "forgot password" never reveal whether an email has an account or is an administrator (SCRUM-62, 63, 68, 69). Failed attempts on unknown emails are blocked the same way, for the same reason.
- **Registration is the one place that does say an email is already in use** (SCRUM-61 AC2 asks for it, so the person can be sent to sign in instead). Sign-in and "forgot password" still do not, so neither of those pages can be used to check who has an account.
- Registration never creates administrators. New accounts are always ordinary users, and `/register` exists only on the main app, not the admin portal (SCRUM-68).

## Other setup choices

- **Blocking is per email, per front end.** Five failures on the main app do not block the same person on the admin portal. Blocking by IP address as well was left out: on a campus network many people share one address.
- **Email in development goes to Mailpit**, so nobody receives a real email while testing. For a demo, set the `SMTP_*` values in the server's `.env` to a real provider (for example Resend, SendGrid or Brevo; all have free tiers).
- **Figma frames are phone-width, but SGJio is a web app.** Below 768px the tabs sit at the bottom, as in Figma. From 768px up they move into the header and the content is centred.
- **Error red is not brand red.** Figma's red (`#F43F5E`) is used for highlights. Form errors use a deeper red (`#DC2626`) so an error never reads as decoration.
