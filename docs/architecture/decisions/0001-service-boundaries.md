# ADR 0001: Four services, split by who owns the data

**Status:** accepted, built (branch `arch/microservices`)

## Context

The monolith (`api/` on `main`) was one FastAPI app over one database. Its modules already fell into groups that change for different reasons and are used by different people: accounts and sign-in (everyone), authoring (administrators), learning (learners), and email (nobody directly). We wanted services that each own a coherent set of tables, so that almost no request needs two of them.

## Decision

| Service          | Owns                                                                                                           | Why it is separate                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **Identity**     | accounts, sessions, credentials, administrators, profile, introduction                                         | Security-sensitive, needed by every request; the only synchronous dependency                   |
| **Content**      | topics, lessons and versions, media, reported problems, the aptitude question bank                             | Written by administrators, published to learners; its own lifecycle (draft, publish, withdraw) |
| **Learning**     | attempts, completions, scores, the aptitude quiz and exemptions, insights; read models of content and learners | Written by learners on every card; the busiest service                                         |
| **Notification** | the email inbox                                                                                                | Slow, failure-prone I/O (SMTP) that should never hold up a request                             |

Three features cross the line and were split by who acts:

- **Aptitude:** the question bank is authored, so it lives in Content; taking the quiz writes the learner's results, so it lives in Learning.
- **Reported problems** are about a card in a version and are handled by administrators, so they live in Content, though learners create them.
- **Lesson insights** are computed from learners' attempts, so they live in Learning, though administrators read them.

The gateway (nginx) is a fifth component with no data of its own.

## Consequences

- Each public path still has exactly one owner, so the front ends did not change: the gateway routes by path prefix.
- Learning needs to know about lessons and learners without calling anyone, which leads to read models (ADR 0007) and events (ADR 0003).
- Four databases and a broker are more to run than one Postgres; Docker Compose starts them all with one command.
- A finer split (for example, aptitude as its own service) was rejected: it would only add events between parts that always change together.
