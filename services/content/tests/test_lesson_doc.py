"""SCRUM-19: what a lesson document may hold, and what still stops it being published."""

import uuid

import pytest
from pydantic import ValidationError

from app.lesson_doc import (
    ChoiceQuestion,
    DuplicateIdError,
    LessonDoc,
    MediaFacts,
    Option,
    StoryCard,
    assign_ids,
    correct_option,
    count_blanks,
    count_words,
    issues,
    stats,
)


def _doc(*cards: dict) -> LessonDoc:
    return LessonDoc.model_validate({"cards": list(cards)})


def _codes(doc: LessonDoc, **context) -> list[str]:
    context = {"title": "Title", "has_topic": True, **context}
    return [issue.code for issue in issues(doc, **context)]


QUESTION = {
    "options": [{"text": "O", "correct": True}, {"text": "C"}],
    "explanation": "O means no milk.",
}


# --- Text ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "blanks"),
    [("No blank", 0), ("Kopi {{blank}}", 1), ("Kopi {{ blank }}", 1), ("{{blank}} {{blank}}", 2)],
)
def test_count_blanks(text, blanks):
    assert count_blanks(text) == blanks


def test_count_words_ignores_markdown_and_blanks():
    assert count_words("**Kopi** is *coffee*.\n\n- One\n- Two\n1. Three") == 6
    assert count_words("Order kopi {{blank}} now") == 3
    assert count_words("[a link](https://example.com)") == 2
    assert count_words("Don't worry lah, kopi-o") == 4


# --- Ids ----------------------------------------------------------------------------------


def test_assign_ids_fills_in_missing_ids_and_keeps_given_ones():
    doc = _doc({"id": "kept", "text": "A", "question": QUESTION}, {"text": "B"})

    assign_ids(doc)

    assert doc.cards[0].id == "kept"
    ids = [doc.cards[0].question.id, doc.cards[1].id]
    ids += [option.id for option in doc.cards[0].question.options]
    assert all(ids) and len(set(ids + ["kept"])) == 5


def test_assign_ids_can_be_deterministic():
    make = lambda path: f"lesson-{path}"  # noqa: E731
    doc = assign_ids(_doc({"text": "A", "question": QUESTION}), make)

    assert doc.cards[0].id == "lesson-c0"
    assert doc.cards[0].question.id == "lesson-c0q"
    assert [o.id for o in doc.cards[0].question.options] == ["lesson-c0q0", "lesson-c0q1"]


def test_a_generated_id_never_repeats_a_given_one():
    doc = _doc({"id": "lesson-c1", "text": "A"}, {"text": "B"})
    assign_ids(doc, lambda path: f"lesson-{path}")
    assert doc.cards[1].id != "lesson-c1"


def test_repeated_ids_are_refused():
    with pytest.raises(DuplicateIdError):
        assign_ids(_doc({"id": "x", "text": "A"}, {"id": "x", "text": "B"}))


def test_documents_refuse_unknown_fields():
    with pytest.raises(ValidationError):
        _doc({"text": "A", "explaination": "typo"})


# --- Correct answers ----------------------------------------------------------------------


def test_a_single_option_is_the_answer_without_marking():
    question = ChoiceQuestion(options=[Option(text="Shiok")])
    assert correct_option(question).text == "Shiok"


def test_the_marked_option_is_the_answer():
    question = ChoiceQuestion(options=[Option(text="A"), Option(text="B", correct=True)])
    assert correct_option(question).text == "B"


@pytest.mark.parametrize("marked", [[], [True, True]])
def test_no_answer_unless_exactly_one_is_marked(marked):
    options = [Option(text=str(n), correct=c) for n, c in enumerate(marked or [False, False])]
    assert correct_option(ChoiceQuestion(options=options)) is None


# --- Issues -------------------------------------------------------------------------------


def test_a_complete_lesson_has_no_issues():
    assert _codes(_doc({"text": "Read me"}, {"text": "Kopi {{blank}}", "question": QUESTION})) == []


def test_lesson_level_blockers():
    assert _codes(LessonDoc(), title="  ", has_topic=False) == [
        "missing_title",
        "missing_topic",
        "no_cards",
    ]
    assert _codes(_doc({"text": "No question anywhere"})) == ["no_questions"]


def test_an_archived_topic_is_only_a_warning():
    found = issues(
        _doc({"text": "Q", "question": QUESTION}), title="T", has_topic=True, topic_archived=True
    )
    assert [(i.code, i.severity) for i in found] == [("topic_archived", "warning")]


@pytest.mark.parametrize(
    ("card", "code", "field"),
    [
        ({"text": "", "question": QUESTION}, "card_text_missing", "text"),
        ({"text": "{{blank}}", "question": QUESTION}, "card_text_missing", "text"),
        ({"text": "{{blank}} and {{blank}}", "question": QUESTION}, "too_many_blanks", "text"),
        (
            {"text": "Q", "question": {**QUESTION, "options": []}},
            "question_no_options",
            "question.options",
        ),
        (
            {"text": "Q", "question": {**QUESTION, "options": [{"text": "A"}, {"text": "B"}]}},
            "question_no_correct",
            "question.options",
        ),
        (
            {
                "text": "Q",
                "question": {
                    **QUESTION,
                    "options": [{"text": "A", "correct": True}, {"text": "B", "correct": True}],
                },
            },
            "question_many_correct",
            "question.options",
        ),
        (
            {
                "text": "Q",
                "question": {
                    **QUESTION,
                    "options": [{"text": "Kopi O", "correct": True}, {"text": "kopi o"}],
                },
            },
            "option_duplicate",
            "question.options",
        ),
        (
            {"text": "Q", "question": {**QUESTION, "explanation": " "}},
            "question_explanation_missing",
            "question.explanation",
        ),
    ],
)
def test_card_blockers(card, code, field):
    doc = assign_ids(_doc({"id": "card", **card}, {"text": "Valid", "question": QUESTION}))
    [issue] = issues(doc, title="T", has_topic=True)
    assert (issue.code, issue.severity, issue.card_id, issue.field) == (
        code,
        "blocker",
        "card",
        field,
    )


def test_a_blank_needs_a_question_on_the_same_card():
    doc = _doc({"text": "Kopi {{blank}}"}, {"text": "Q", "question": QUESTION})
    assert _codes(doc) == ["blank_without_question"]


def test_an_empty_option_names_the_option():
    question = {**QUESTION, "options": [{"id": "o1", "text": "", "correct": True}, {"text": "B"}]}
    [issue] = issues(_doc({"text": "Q", "question": question}), title="T", has_topic=True)
    assert (issue.code, issue.field) == ("option_text_missing", "question.options.o1")


def test_a_single_option_needs_no_marking():
    question = {"options": [{"text": "Shiok"}], "explanation": "Delicious."}
    assert _codes(_doc({"text": "Say {{blank}}", "question": question})) == ["no_scored_question"]
    assert (
        _codes(
            _doc(
                {"text": "Say {{blank}}", "question": question},
                {"text": "Quiz", "question": QUESTION},
            )
        )
        == []
    )


def test_long_cards_and_lessons_are_warnings_not_blockers():
    long_card = {"text": "word " * 51}
    doc = _doc(*[long_card] * 9, {"text": "Q", "question": QUESTION})
    found = issues(doc, title="T", has_topic=True)
    assert {i.code for i in found} == {"card_text_long", "long_lesson"}
    assert all(i.severity == "warning" for i in found)


def test_blockers_come_before_warnings():
    doc = _doc({"text": "word " * 60}, {"text": "Kopi {{blank}}"})
    severities = [i.severity for i in issues(doc, title="", has_topic=True)]
    assert severities == sorted(severities)  # "blocker" < "warning"


def test_media_issues():
    image_id, audio_id, gone_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    media = {
        image_id: MediaFacts("image", width=1000, height=1000),
        audio_id: MediaFacts("audio", duration_ms=25_000),
    }
    doc = _doc(
        {"text": "A", "image": {"asset_id": str(image_id)}, "audio": {"asset_id": str(audio_id)}},
        {"text": "B", "image": {"asset_id": str(gone_id)}},
        {"text": "C", "audio": {"asset_id": str(image_id)}, "question": QUESTION},
    )
    assert _codes(doc, media=media) == [
        "image_missing",
        "audio_missing",
        "image_alt_missing",
        "image_shape",
        "audio_transcript_missing",
        "audio_long",
    ]


# --- Stats --------------------------------------------------------------------------------


def test_stats_count_what_a_learner_reads_and_hears():
    audio_id = uuid.uuid4()
    doc = LessonDoc(
        cards=[
            StoryCard(text="one two three"),
            StoryCard(
                text="four {{blank}}",
                audio={"asset_id": audio_id, "transcript": ""},
                question=ChoiceQuestion(
                    options=[Option(text="five", correct=True), Option(text="six")],
                    explanation="seven eight",
                ),
            ),
            StoryCard(text="tap", question=ChoiceQuestion(options=[Option(text="nine")])),
        ]
    )

    result = stats(doc, {audio_id: MediaFacts("audio", duration_ms=4_400)})

    assert result.cards == 3
    assert result.questions == 2
    assert result.scored_questions == 1
    assert result.words == 10
    assert result.audio_seconds == 4
    assert result.reading_seconds == 3 + 4  # 10 words at 200 a minute, plus the audio
