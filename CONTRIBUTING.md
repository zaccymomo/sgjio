# Working on SGJio

## Branches

- `main` is always working. Nobody pushes to it directly.
- Work on a branch named after the Jira issue: `SCRUM-61-register`, `SCRUM-43-progress-circles`.
- Keep branches short-lived. Pull `main` into your branch often.

## Commits

Start each message with the Jira key, so Jira links the commit to the issue:

```
SCRUM-61: add registration form and validation
```

## Pull requests

1. Push your branch and open a pull request into `main`. The template asks for the Jira key and the acceptance criteria you checked.
2. CI runs lint, type checks, API tests and both builds. It must pass.
3. **At least one teammate reviews and approves** before merging.
4. Merge with "Squash and merge", then delete the branch.

## Branch protection (one-time, repository owner)

GitHub → repository → **Settings → Branches → Add branch ruleset** (or "Add rule") for `main`:

- Require a pull request before merging, with **1 required approval**
- Require status checks to pass: select **API** and **Front end** (they appear after CI has run once)
- Block force pushes

## Before you push

```bash
cd api && ruff check . && ruff format . && pytest && cd ..
npm run lint && npm run format && npm run typecheck
```

## Changing the database

1. Edit `api/app/models.py`.
2. `cd api && alembic revision --autogenerate -m "short description"`
3. **Read the generated file** in `api/alembic/versions/` and fix anything Alembic guessed wrong.
4. `alembic upgrade head`, then run the tests.
5. Commit the model change and the migration together.

Never edit a migration that is already on `main`. Add a new one instead.

## Secrets

Real passwords, API keys and SMTP credentials go in `api/.env`, which git ignores. Add new settings to `api/.env.example` with a safe placeholder so teammates know they exist.
