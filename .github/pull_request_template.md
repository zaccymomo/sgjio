## Jira issue

SCRUM-

## What changed

<!-- One or two sentences. -->

## Acceptance criteria checked

<!-- Copy the story's criteria and tick the ones this PR meets. -->

- [ ] AC1
- [ ] AC2

## Screenshots

<!-- For UI changes: phone width (375px) and desktop. -->

## Checklist

- [ ] Tests added or updated (`services/<name>`: `.venv/bin/python -m pytest`; `scripts/e2e.sh` if a flow crosses services)
- [ ] Lint and format pass (`ruff`, `npm run lint`, `npm run format:check`)
- [ ] New database changes have a reviewed migration in the owning service's `alembic/versions/`
- [ ] Event changes are in `contracts/events/` and `contracts/validate.py` passes
- [ ] New settings added to the service's `app/config.py`, `docker-compose.yml` and `.env.example` (if it has one)
