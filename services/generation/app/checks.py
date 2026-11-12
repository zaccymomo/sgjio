"""The checks in code every written lesson must pass (docs/ai-lessons-plan.md, step 5.2).

`problems(lesson, brief)` returns a list of plain sentences, empty when the lesson is fine.
They are sent back to the model for its one retry, so they say what to fix.

The limits are a little stricter than Content's lesson rules (services/content/app/
lesson_doc.py) so a generated lesson always passes them, and within the event contract
(contracts/events/content.lesson_version.published.schema.json, $defs/card).
"""

import re

from app.llm import LessonOut

BLANK = re.compile(r"\{\{\s*blank\s*\}\}")
WORD = re.compile(r"[A-Za-z0-9À-ɏ'’]+")

TITLE_MAX = 80
SUMMARY_MAX = 160
POINTS_MIN, POINTS_MAX, POINT_MAX = 1, 4, 160
CARD_WORDS_MAX = 70
CARD_CHARS_MAX = 1500
OPTIONS_MIN, OPTIONS_MAX = 2, 4
OPTION_MAX = 160
WHY_NOT_MAX = 400
EXPLANATION_MAX = 800

# HTML tags, Markdown links and images, and bare web addresses.
LINK_OR_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>|!?\[[^\]]*\]\([^)]*\)|https?://|www\.")

# Claims the app must never make (CLAUDE.md: nothing implies PR or immigration benefits).
# Whole words only, so "PR" never matches "price" or "April", nor "ICA" "musical".
BANNED = [
    (re.compile(r"\bPRs?\b", re.IGNORECASE), "mentions PR"),
    (re.compile(r"\bpermanent\s+residen\w*", re.IGNORECASE), "mentions permanent residence"),
    (re.compile(r"\bcitizenship\b", re.IGNORECASE), "mentions citizenship"),
    (re.compile(r"\bICA\b", re.IGNORECASE), "mentions ICA"),
    (re.compile(r"\bimmigration\s+outcomes?\b", re.IGNORECASE), "mentions immigration outcomes"),
    (re.compile(r"\bguarantee\w*", re.IGNORECASE), 'says "guarantee"'),
    (
        re.compile(r"\bimprov\w*\s+(?:your|their|his|her|one's)\s+chances\b", re.IGNORECASE),
        'says "improve your chances"',
    ),
    # A web app: "select", not "tap". "tap" about a card at a gantry, tap water, or
    # tapping in and out on the MRT is everyday Singapore and is allowed.
    (
        re.compile(
            r"\btap\b(?!\s+(?:water|in\b|out\b|your\s+(?:ez-?link|card|phone|watch)|"
            r"(?:the|a)\s+(?:gantry|reader)))",
            re.IGNORECASE,
        ),
        'says "tap" (use "select")',
    ),
]


def count_words(text: str) -> int:
    return len(WORD.findall(BLANK.sub(" ", text)))


def all_text(lesson: LessonOut) -> list[str]:
    texts = [lesson.title, lesson.summary, *lesson.learning_points]
    for card in lesson.cards:
        texts.append(card.text)
        if card.question is not None:
            texts.append(card.question.explanation)
            for option in card.question.options:
                texts += [option.text, option.why_not]
    return texts


def problems(lesson: LessonOut, brief: dict) -> list[str]:
    found: list[str] = []

    # Shape and length of the lesson as a whole
    if not lesson.title.strip():
        found.append("The title is missing.")
    elif len(lesson.title) > TITLE_MAX:
        found.append(f"The title is over {TITLE_MAX} characters.")
    if not lesson.summary.strip():
        found.append("The summary is missing.")
    elif len(lesson.summary) > SUMMARY_MAX:
        found.append(f"The summary is over {SUMMARY_MAX} characters.")
    if not POINTS_MIN <= len(lesson.learning_points) <= POINTS_MAX:
        found.append(f"Give {POINTS_MIN} to {POINTS_MAX} learning points.")
    for i, point in enumerate(lesson.learning_points, 1):
        if not point.strip() or len(point) > POINT_MAX:
            found.append(f"Learning point {i} must be 1 to {POINT_MAX} characters.")

    questions = [card.question for card in lesson.cards if card.question is not None]
    if len(lesson.cards) != brief["cards"]:
        found.append(f"Write exactly {brief['cards']} cards (there are {len(lesson.cards)}).")
    if len(questions) != brief["questions"]:
        found.append(f"Ask exactly {brief['questions']} questions (there are {len(questions)}).")

    # Each card
    for n, card in enumerate(lesson.cards, 1):
        if not card.text.strip():
            found.append(f"Card {n} has no text.")
        if count_words(card.text) > CARD_WORDS_MAX:
            found.append(f"Card {n} is over {CARD_WORDS_MAX} words.")
        if len(card.text) > CARD_CHARS_MAX:
            found.append(f"Card {n} is over {CARD_CHARS_MAX} characters.")
        blanks = len(BLANK.findall(card.text))
        if blanks > 1:
            found.append(f"Card {n} has more than one {{{{blank}}}}.")
        if blanks and card.question is None:
            found.append(f"Card {n} has a {{{{blank}}}} but no question.")
        question = card.question
        if question is None:
            continue
        if not OPTIONS_MIN <= len(question.options) <= OPTIONS_MAX:
            found.append(f"Card {n}'s question needs {OPTIONS_MIN} to {OPTIONS_MAX} options.")
        if sum(1 for option in question.options if option.correct) != 1:
            found.append(f"Card {n}'s question needs exactly one correct option.")
        if not question.explanation.strip():
            found.append(f"Card {n}'s question has no explanation.")
        elif len(question.explanation) > EXPLANATION_MAX:
            found.append(f"Card {n}'s explanation is over {EXPLANATION_MAX} characters.")
        for m, option in enumerate(question.options, 1):
            if not option.text.strip() or len(option.text) > OPTION_MAX:
                found.append(f"Card {n}, option {m} must be 1 to {OPTION_MAX} characters.")
            if len(option.why_not) > WHY_NOT_MAX:
                found.append(f"Card {n}, option {m}'s why_not is over {WHY_NOT_MAX} characters.")

    # Words and markup anywhere
    text = "\n".join(all_text(lesson))
    if LINK_OR_HTML.search(text):
        found.append("Remove HTML, links and images.")
    for pattern, reason in BANNED:
        if pattern.search(text):
            found.append(f"The lesson {reason}; remove it.")
    return found
