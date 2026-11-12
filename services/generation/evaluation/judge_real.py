"""Can each answer-check model catch the real lessons our blind graders blocked?

    python -m evaluation.judge_real RESULTS.jsonl GRADING_DIR OUT.jsonl --models a,b

Takes every lesson the graders blocked and the same number of the best-graded unblocked
ones, gives each to every check model as the app would (the case's grounding), and records
whether it said ok. Needs GENERATION_BASE_URL and GENERATION_API_KEY.
"""

import argparse
import json
from pathlib import Path

from app import prompt
from app.llm import BadOutput, ProviderError, parse_verdict
from evaluation.cases import CASES
from evaluation.run import TimedLLM, run_per_model

BY_KEY = {case["key"]: case for case in CASES}


def as_written(lesson: dict) -> dict:
    """The generated result back in the shape the model wrote (what the check reads)."""
    return {
        "title": lesson["title"],
        "summary": lesson["summary"],
        "learning_points": lesson["learning_points"],
        "cards": [
            {
                "text": card["text"],
                "question": card["question"]
                and {
                    "explanation": card["question"]["explanation"],
                    "options": [
                        {k: option[k] for k in ("text", "correct", "why_not")}
                        for option in card["question"]["options"]
                    ],
                },
            }
            for card in lesson["doc"]["cards"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("grading")
    parser.add_argument("out")
    parser.add_argument("--models", required=True)
    args = parser.parse_args()
    grading = Path(args.grading)
    key = json.loads((grading / "key.json").read_text())
    grades = [json.loads(line) for line in (grading / "grades.jsonl").read_text().splitlines()]
    records = {
        (r["model"], r["case"], r["run"]): r
        for r in map(json.loads, Path(args.results).read_text().splitlines())
    }

    def overall(grade):
        return sum(grade[s] for s in ("accuracy", "relevance", "language", "questions"))

    blocked = [g for g in grades if g["block"]]
    good = sorted((g for g in grades if not g["block"]), key=overall, reverse=True)
    picked = [(g, False) for g in blocked] + [(g, True) for g in good[: len(blocked)]]
    items = []
    for grade, expected_ok in picked:
        k = key[grade["id"]]
        record = records[(k["model"], k["case"], k["run"])]
        items.append(
            {
                "id": grade["id"],
                "expected_ok": expected_ok,
                "lesson": as_written(record["lesson"]),
                "grounding": BY_KEY[k["case"]]["grounding"],
            }
        )

    def check(model: str, item: dict) -> dict:
        llm = TimedLLM(model, model)
        said, error = None, None
        try:
            said = parse_verdict(
                llm.judge(prompt.judge_messages(item["grounding"], item["lesson"]))
            ).ok
        except (ProviderError, BadOutput) as failure:
            error = str(failure)
        return {
            "mode": "judge",
            "model": model,
            "case": item["id"],
            "expected_ok": item["expected_ok"],
            "said_ok": said,
            "problems": None,
            "error": error,
            "seconds": round(sum(c["seconds"] for c in llm.calls), 1),
        }

    out = Path(args.out)

    def jobs(model):
        return [(lambda m=model, i=item: check(m, i)) for item in items]

    run_per_model(args.models.split(","), jobs, out, workers=5)


if __name__ == "__main__":
    main()
