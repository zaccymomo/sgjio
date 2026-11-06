"""What Identity's and Content's seeds publish, played through the consumer: the six seed
topics with lessons at several levels (one of them the "Lah, Leh and Lor" lesson the demo
plants a confusing question in), a ready aptitude bank with seed keys, and the seed users."""

from app.seed import TEST_USERS, TOPICS

LAH = {
    "cards": [
        {"id": "intro", "text": "Particles change a sentence's mood."},
        {
            "id": "c1",
            "text": "Can or not {{blank}}?",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "a", "text": "ah", "correct": True},
                    {"id": "b", "text": "lor"},
                ],
                "explanation": "Ah asks.",
            },
        },
        {
            "id": "c2",
            "text": '"Okay lor" means they {{blank}}.',
            "question": {
                "id": "q2",
                "options": [
                    {"id": "resigned", "text": "Accept it, reluctantly", "correct": True},
                    {"id": "agree", "text": "They fully agree"},
                    {"id": "angry", "text": "They are angry"},
                ],
                "explanation": "Lor sounds resigned.",
            },
        },
    ]
}


def seed_world(content, identity, seed_email="newcomer@sgjio.example.com"):
    topics = [content.topic(name, position) for position, name in enumerate(TOPICS)]
    lessons = {}
    for topic in topics:
        for n, level in enumerate((1, 1, 2, 3)):
            title = (
                "Lah, Leh and Lor"
                if (topic.name, n) == ("Singlish", 0)
                else (f"{topic.name} lesson {n + 1}")
            )
            lessons[title] = content.lesson(
                topic,
                title,
                level=level,
                position=n,
                doc=LAH if title == "Lah, Leh and Lor" else None,
                key=f"{topic.name.lower()}-{n + 1}",
            )
    content.full_bank(topics)
    identity.register("admin@sgjio.example.com", role="admin")
    identity.register(seed_email)
    for email in TEST_USERS:
        identity.register(email)
    return topics, lessons
