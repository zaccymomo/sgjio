# Data model (SCRUM-72)

Defined in `api/app/models.py` and created by the migrations in `api/alembic/versions/`.

```mermaid
erDiagram
    users ||--o| profiles : "has"
    users ||--o{ auth_sessions : "signed in on"
    users ||--o{ password_reset_tokens : "requested"
    topics ||--o{ lessons : "contains"
    lessons ||--o| quiz_questions : "ends with"
    quiz_questions ||--|{ quiz_options : "offers"

    users {
        uuid id PK
        string name
        string email UK "stored lower-case"
        string password_hash "Argon2"
        string role "user | admin"
        string user_type "newcomer | singaporean | null for admins"
        timestamptz created_at
    }
    profiles {
        uuid user_id PK,FK
        string neighbourhood
        string_array interests
        string_array languages
    }
    topics {
        uuid id PK
        string name UK "unique ignoring case"
    }
    lessons {
        uuid id PK
        string title
        text content "Markdown"
        uuid topic_id FK "may be empty while a draft"
        string status "draft | published | withdrawn"
        timestamptz published_at
        timestamptz withdrawn_at
        timestamptz updated_at "indexed: admin list sorts by it"
    }
    quiz_questions {
        uuid id PK
        uuid lesson_id FK,UK "one question per lesson"
        text prompt
        text explanation "shown after answering"
    }
    quiz_options {
        uuid id PK
        uuid question_id FK
        string text
        bool is_correct "at most one true per question"
        int position
    }
    auth_sessions {
        uuid id PK
        uuid user_id FK
        string scope "app | admin"
        string token_hash UK "SHA-256 of the cookie"
        timestamptz expires_at
    }
    password_reset_tokens {
        uuid id PK
        uuid user_id FK
        string scope "app | admin"
        string token_hash UK
        timestamptz expires_at "5 minutes"
        timestamptz used_at
    }
    login_attempts {
        int id PK
        string email
        string scope "app | admin"
        bool succeeded
        timestamptz attempted_at
    }
```

## Why it looks like this

- **One `users` table for users and administrators.** `role` separates them. Administrators are not created by registration; they are seeded or added with `python -m app.cli create-admin` (SCRUM-68 open decision).
- **Users and administrators have separate sessions.** `scope` on a session or reset link says which front end it belongs to. An admin-portal session never opens main-app routes, and the reverse holds too.
- **Tokens are stored hashed.** The raw session and reset tokens only exist in the browser cookie or the emailed link. A copy of the database cannot be used to sign in.
- **A lesson belongs to one topic.** This keeps the progress-circle arithmetic simple, as assumed in SCRUM-56. A draft may have no topic yet; publishing requires one.
- **Withdrawn lessons are kept, not deleted** (`status = withdrawn`), so users' history still shows lessons they completed (SCRUM-52 AC4).
- **Enumerations are stored as text with a CHECK constraint**, not native Postgres enums, so adding a value later is a simple migration.
- **Quiz attempts and progress are not here yet.** SCRUM-16 adds them as a new migration on top of this one.

## Seed data

`python -m app.cli seed` is safe to run repeatedly. It adds:

- one administrator and one Newcomer user (see README for the sign-in details)
- the six topics from the Figma home screen: Singlish, Hawker & Food, Workplace, Public Etiquette, Festivals, Getting Around
- one published sample lesson with a four-option quiz: "Ordering at a Local Hawker Centre"
