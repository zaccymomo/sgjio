# ADR 0008: Account deletion as an event-driven saga

**Status:** accepted, built

## Context

In the monolith, deleting an account was one transaction: foreign keys cascaded to sessions, progress and quiz results, and nulled the reporter on reported problems. Now the data lives in three databases (ADR 0002), and no transaction spans them.

## Decision

A choreographed saga with one command and two reactions, no coordinator:

1. **Identity** (`POST /api/auth/delete-account`, after the password or a fresh Google token confirms it): in one transaction, delete the user (sessions, reset links and profile cascade), delete their sign-in history, and write `identity.user.deleted` to the outbox. The cookie is cleared. From the next request on, the gateway's session check fails, so the user can no longer read or write anything.
2. **Learning** consumes the event (`app/erasure.py`): in one transaction, under the learner's advisory lock, add the id to `erased_learners` (a tombstone kept for good), then delete their attempts and answers, completions, aptitude quiz and exemptions, and the `learners` row.
3. **Content** consumes the event (`app/erasure.py`): in one transaction, under the user's advisory lock, add the id to `erased_users` (a tombstone kept for good), then null it wherever it appears (`lesson_reports.reporter_id` and `resolved_by`, `lesson_versions.published_by`, `media_assets.created_by`).

There are no compensating steps because nothing can be refused: Identity's step is the decision, and the reactions only remove data. Each reaction is repeatable, so a redelivered event is harmless.

## Consequences

- The account is gone at once; the learner's progress and reporter links are erased **within seconds** instead of in the same commit (declared behaviour change; e2e `test_deleting_an_account_erases_its_learning_data`).
- The event is committed with the delete, so it cannot be lost or sent for a delete that rolled back. If Learning or Content is down, it waits in their queue.
- **A request already in flight** is the one gap, and both consumers close it the same way. In Learning, starting an attempt and submitting the quiz (the only writes that create a learner's first rows) take the same advisory lock in shared mode and refuse an erased id. In Content, reporting a problem (the only learner write that records a user id) does the same. Either the write commits before the erasure (and is erased with the rest) or it is refused with 401.
- **Replays cannot resurrect a user:** `user.registered` is refused for an id in `erased_learners`, and `user.deleted` has a higher version than `user.registered`.
- Lesson insights count learners from Learning's own `learners` table, so a deleted learner drops out of them once erased.
