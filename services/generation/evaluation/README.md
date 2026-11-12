# Model evaluation

How we chose the NUS SoC LaaS models for AI-generated lessons. The results and decision are in
`docs/ai-model-evaluation.md`; this folder is the harness, so anyone can run it again (models
on SoC LaaS change).

Every request goes through the real pipeline (`app/prompt.py`, `app/checks.py`, one retry,
the answer check), so the numbers are what the app would see.

## What it runs

- `cases.py`
  - **16 requests:** 8 learner requests (every topic; both focuses; levels 1 to 4; short
    and usual length; with and without text), 2 admin drafts from notes, and 6 hostile or
    odd requests (a PR essay, prompt injection, a racial stereotype, fare evasion,
    gibberish, a PR claim).
  - **14 labelled lessons** for the answer-check model: 6 good, and 8 with one planted
    problem each (a wrong answer, a PR claim, a stereotype, a contradiction of the
    grounding, two right answers, unsafe advice, made-up Singlish, a wrong cultural fact).
  - **Grounding** comes from the real seed lessons: `fixtures/seed_lessons.json`, exported
    from `content/lessons`.
- `run.py write`: runs the requests through each model (`--check-model none` measures the
  writer alone) and records the outcome, timings, retries, first-try check problems and
  prompt leaks.
- `run.py judge`: gives each labelled lesson to each model as the answer check.
- `run.py report`: makes the tables.
- `textbox.py`: what happens to odd text in the learner's box (gibberish, vague, off-topic,
  harmful, injection, a different topic, a normal request).
- `grading.py`: exports generated lessons blind (random ids) for quality grading, then
  scores them per model.

## Running it

From `services/generation`, with the key in your shell, never in a file in git:

```bash
export GENERATION_BASE_URL=https://soclaas-api.comp.nus.edu.sg/v1 GENERATION_API_KEY=...
.venv/bin/python -m evaluation.run write evaluation/results/screen.jsonl --models a,b --cases screen --check-model none
.venv/bin/python -m evaluation.run write evaluation/results/full.jsonl --models a,b --cases all --runs 2 --check-model none
.venv/bin/python -m evaluation.run judge evaluation/results/judge.jsonl --models a,b
.venv/bin/python -m evaluation.run report evaluation/results/*.jsonl
.venv/bin/python -m evaluation.grading export evaluation/results/full.jsonl evaluation/results/grading
```

`evaluation/results/` is git-ignored: it holds raw model output.
