"""Blind quality grading of generated lessons (evaluation/README.md).

    python -m evaluation.grading export RESULTS.jsonl OUT_DIR   # lessons.md + key.json
    python -m evaluation.grading score OUT_DIR                  # grades.jsonl + key.json -> table

`export` writes every generated lesson for the ordinary (non-hostile) cases with the model
replaced by a random id, so the grader can't tell which model wrote what. The grader writes
grades.jsonl: one {"id", "accuracy", "relevance", "language", "questions", "block", "note"}
per lesson, each score 1 to 5, block true if it must not reach a learner.
"""

import json
import random
import sys
from pathlib import Path

from evaluation.cases import CASES

BY_KEY = {case["key"]: case for case in CASES}
SCORES = ("accuracy", "relevance", "language", "questions")


def request_text(case: dict) -> str:
    brief = case["brief"]
    lines = [
        f"Topic: {brief['topic']['name']}; focus: {brief['focus']}; level {brief['level']} of 5; "
        f"{brief['cards']} cards, {brief['questions']} question(s); audience: {brief['audience']}"
    ]
    if brief["ask"]:
        lines.append(f"Learner asked: {brief['ask']}")
    if brief["notes"]:
        lines.append(f"Admin notes: {brief['notes']}")
    for mistake in case["grounding"]["mistakes"]:
        lines.append(
            f'Mistake to re-teach: "{mistake["card_text"][:120]}" (chose "{mistake["chosen"]}";'
            f' right: "{mistake["correct"]}")'
        )
    return "\n".join(lines)


def lesson_text(lesson: dict) -> str:
    lines = [f"**{lesson['title']}**: {lesson['summary']}", ""]
    for number, card in enumerate(lesson["doc"]["cards"], 1):
        lines.append(f"{number}. {card['text']}")
        question = card["question"]
        if question:
            for option in question["options"]:
                mark = "(correct)" if option["correct"] else f"(wrong: {option['why_not']})"
                lines.append(f"   - {option['text']} {mark}")
            lines.append(f"   Explanation: {question['explanation']}")
    return "\n".join(lines)


def export(results: str, out_dir: str) -> None:
    records = [json.loads(line) for line in Path(results).read_text().splitlines()]
    lessons = [r for r in records if r.get("lesson") and r["expect"] == "lesson"]
    random.Random(4301).shuffle(lessons)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key, parts = {}, []
    for index, record in enumerate(lessons, 1):
        lesson_id = f"L{index:03d}"
        key[lesson_id] = {"model": record["model"], "case": record["case"], "run": record["run"]}
        parts.append(
            f"## {lesson_id}\n\nRequest:\n{request_text(BY_KEY[record['case']])}\n\n"
            f"Lesson:\n{lesson_text(record['lesson'])}\n"
        )
    (out / "lessons.md").write_text("\n".join(parts))
    (out / "key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"{len(lessons)} lessons -> {out / 'lessons.md'}")


def score(out_dir: str) -> None:
    out = Path(out_dir)
    key = json.loads((out / "key.json").read_text())
    grades = [json.loads(line) for line in (out / "grades.jsonl").read_text().splitlines() if line]
    per_model: dict[str, list[dict]] = {}
    for grade in grades:
        per_model.setdefault(key[grade["id"]]["model"], []).append(grade)
    print("| Model | Graded | Accuracy | Relevance | Language | Questions | Overall | Blocked |")
    print("|---|---|---|---|---|---|---|---|")
    for model, mine in sorted(per_model.items()):
        means = [sum(g[s] for g in mine) / len(mine) for s in SCORES]
        print(
            f"| {model} | {len(mine)} | "
            + " | ".join(f"{m:.1f}" for m in means)
            + f" | {sum(means) / len(means):.2f} | {sum(bool(g['block']) for g in mine)} |"
        )


if __name__ == "__main__":
    {"export": lambda: export(sys.argv[2], sys.argv[3]), "score": lambda: score(sys.argv[2])}[
        sys.argv[1]
    ]()
