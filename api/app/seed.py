"""Development seed data (SCRUM-72). Safe to run more than once.

Creates:
- one administrator (administrators are not created through registration, SCRUM-68)
- one ordinary Newcomer account, so the main app can be signed in to before SCRUM-61
- the six topics from the Figma home screen
- three published lessons per topic, each with its single quiz question (SCRUM-58)
- some completed lessons for the Newcomer account, so the landing page circles have
  something to show while SCRUM-15 (answering a quiz) is still to be built

Every lesson is short enough to read in under two minutes (SCRUM-6 AC3).

Topics and lessons get a position only when the seed creates them, appended after anything
already there, so a fresh database gets the Figma order and re-seeding never undoes an
order an administrator has set (SCRUM-66).
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import normalise_email
from app.config import get_settings
from app.lessons import next_lesson_position
from app.models import (
    Lesson,
    LessonCompletion,
    LessonStatus,
    Profile,
    QuizOption,
    QuizQuestion,
    Topic,
    User,
    UserRole,
    UserType,
)
from app.security import hash_password
from app.topics import next_topic_position

# In the Figma home screen's order, which is the order a fresh database starts in.
TOPICS = [
    "Singlish",
    "Hawker & Food",
    "Workplace",
    "Public Etiquette",
    "Festivals",
    "Getting Around",
]

# Each lesson: one topic, a short body, and exactly one single-choice question whose
# options are (text, is_correct). Exactly one option per question is correct (SCRUM-15 AC2).
LESSONS: list[dict] = [
    # --- Singlish ---------------------------------------------------------------------
    {
        "topic": "Singlish",
        "title": "Lah, Leh and Lor",
        "content": (
            "Singlish particles sit at the end of a sentence and carry the tone. They are "
            "not filler, and swapping one for another changes what you mean.\n\n"
            '- **Lah** softens or insists: *"Don\'t worry lah"* is reassuring.\n'
            '- **Leh** softens a disagreement or a request: *"But I already paid leh."*\n'
            '- **Lor** signals resignation: *"Then cancel lor."*\n'
            '- **Meh** questions something you doubt: *"Really free meh?"*\n\n'
            "You do not have to use them. Recognising them matters far more, because a "
            'colleague saying *"Can lah"* and *"Can meh?"* means opposite things.'
        ),
        "prompt": 'A colleague replies to your plan with "Can meh?". What are they signalling?',
        "explanation": (
            '"Meh" marks doubt, so "Can meh?" is a polite way of questioning whether the '
            "plan will actually work, not agreeing to it."
        ),
        "options": [
            ("They doubt it will work", True),
            ("They fully agree", False),
            ("They are annoyed with you", False),
            ("They did not hear you", False),
        ],
    },
    {
        "topic": "Singlish",
        "title": "Words You Will Hear Every Day",
        "content": (
            "A handful of borrowed words do a lot of work in everyday Singapore English.\n\n"
            "- **Shiok**: intensely satisfying, usually food.\n"
            "- **Sian**: bored, weary, fed up.\n"
            '- **Makan**: to eat, or a meal. *"Go makan?"*\n'
            "- **Chope**: to reserve a seat.\n"
            '- **Alamak**: an exclamation of dismay, like "oh no".\n'
            "- **Kiasu**: afraid of losing out; describes someone who queues early for "
            "everything.\n\n"
            "These are normal in offices and among friends. Using one or two naturally is "
            "welcomed; forcing all of them into one sentence is not."
        ),
        "prompt": (
            'Your colleague finishes lunch and says the laksa was "shiok". What do they mean?'
        ),
        "explanation": '"Shiok" means intensely satisfying or delicious. They enjoyed it.',
        "options": [
            ("It was delicious", True),
            ("It was too spicy", False),
            ("It was overpriced", False),
            ("It was disappointing", False),
        ],
    },
    {
        "topic": "Singlish",
        "title": "Why Sentences Sound Shorter",
        "content": (
            "Singlish often drops words English speakers expect, because its grammar borrows "
            "from Chinese dialects and Malay.\n\n"
            '- Subjects disappear when obvious: *"Went already"* for "I already went".\n'
            "- **Already** marks a completed action, where British English uses a tense: "
            '*"I eat already"* means "I have eaten".\n'
            '- **Got** marks existence: *"Got queue or not?"* means "Is there a queue?"\n\n'
            "None of this is broken English. It is a consistent local grammar, and hearing "
            "it as a system rather than as mistakes makes it far easier to follow."
        ),
        "prompt": 'A hawker says "Sold out already". What does "already" do here?',
        "explanation": (
            '"Already" marks the action as complete, the way a perfect tense does in '
            "British English: the stall has sold out."
        ),
        "options": [
            ("Marks the action as completed", True),
            ("Means it happened unusually early", False),
            ("Adds politeness", False),
            ("Asks you to confirm", False),
        ],
    },
    # --- Hawker & Food ----------------------------------------------------------------
    {
        "topic": "Hawker & Food",
        "title": "Ordering at a Local Hawker Centre",
        "content": (
            "## Chope first, then order\n\n"
            'At busy hawker centres, people reserve ("chope") a seat by leaving a packet of '
            "tissues on the table. Find a free seat before you queue.\n\n"
            "## Kopi lingo\n\n"
            "- **Kopi**: coffee with condensed milk\n"
            "- **Kopi O**: black coffee with sugar\n"
            "- **Kopi C**: coffee with evaporated milk and sugar\n"
            "- **Kosong**: no sugar\n"
            "- **Siew dai**: less sugar\n"
        ),
        "prompt": "You want black coffee with no sugar. What do you ask for?",
        "explanation": (
            '"O" means no milk and "kosong" means no sugar, so black coffee with no sugar '
            "is Kopi O Kosong."
        ),
        "options": [
            ("Kopi C", False),
            ("Kopi O Kosong", True),
            ("Kopi Siew Dai", False),
            ("Kopi", False),
        ],
    },
    {
        "topic": "Hawker & Food",
        "title": "Return Your Tray",
        "content": (
            "Since 2021, clearing your table at hawker centres, coffee shops and food courts "
            "is required, not optional. Enforcement began with warnings and now carries "
            "fines.\n\n"
            "Look for the tray return racks near the entrance or along a wall. Most have "
            "separate points for halal and non-halal crockery, marked in green and blue, "
            "because Muslim diners and stallholders need their utensils kept apart. Put "
            "leftovers and tissues in the bin, and stack the tray on the matching rack.\n\n"
            "Cleaners still work the tables, but they are there for wiping down, not for "
            "carrying your plates away."
        ),
        "prompt": "Why do tray return racks have separate halal and non-halal points?",
        "explanation": (
            "Crockery used for non-halal food is kept apart from halal crockery so that "
            "Muslim diners and stallholders are not affected by cross-contamination."
        ),
        "options": [
            ("To keep halal and non-halal crockery separate", True),
            ("To sort plates by which stall they came from", False),
            ("To separate plastic from ceramic for recycling", False),
            ("To divide the work between two cleaning companies", False),
        ],
    },
    {
        "topic": "Hawker & Food",
        "title": "Sharing a Table",
        "content": (
            "At peak lunch hours you will often be asked to share a table with strangers. "
            'The usual opener is *"Excuse me, anyone sitting here?"* or simply a gesture at '
            "the empty chair.\n\n"
            "Saying yes is normal and expected. It is not an invitation to conversation: "
            "most people eat, keep to their half of the table and leave. Neither side is "
            "being unfriendly.\n\n"
            "If a packet of tissues or an umbrella is on the table, the seat is choped and "
            "someone is queueing for it. Leave it and look elsewhere."
        ),
        "prompt": (
            "A stranger gestures at the empty seat at your table during lunch rush. "
            "What is expected?"
        ),
        "explanation": (
            "Sharing tables at peak hours is normal. You nod or say yes; neither of you is "
            "expected to make conversation."
        ),
        "options": [
            ("Agree to share, conversation not expected", True),
            ("Refuse, since you were there first", False),
            ("Agree, and introduce yourself properly", False),
            ("Move to a different table yourself", False),
        ],
    },
    # --- Workplace --------------------------------------------------------------------
    {
        "topic": "Workplace",
        "title": "Names and Titles at Work",
        "content": (
            "Singapore offices are less formal than much of the region, but seniority still "
            "shows in how people address each other.\n\n"
            "- First names are common among peers, and with managers at most companies.\n"
            "- Many Chinese Singaporeans have an English name alongside their given name; "
            "use whichever they introduce themselves with.\n"
            "- Some colleagues, especially in older or government organisations, are "
            "addressed as **Mr** or **Ms** plus surname.\n"
            "- **Sir** and **Ma'am** appear in uniformed and some client-facing roles.\n\n"
            "The safe approach: copy how the person signs their emails, and how others in "
            "the room address them."
        ),
        "prompt": "You are unsure how to address a senior colleague. What is the safest approach?",
        "explanation": (
            "Following how they sign their own emails, and how the rest of the team addresses "
            "them, matches the norm of that particular workplace."
        ),
        "options": [
            ("Copy how they sign emails and how others address them", True),
            ("Always use Mr or Ms plus surname", False),
            ("Always use their first name", False),
            ('Use "Sir" or "Ma\'am" until told otherwise', False),
        ],
    },
    {
        "topic": "Workplace",
        "title": "Saying No Without Saying No",
        "content": (
            "Direct refusal is often avoided, so disagreement arrives softened. Phrases that "
            "usually mean no, or not yet:\n\n"
            '- *"I will try my best"* when no commitment is being made.\n'
            '- *"Let me check and get back to you"* with no follow-up.\n'
            '- *"Quite challenging leh"* meaning it will not happen on that timeline.\n'
            "- Silence in a meeting after a proposal.\n\n"
            "This is about preserving face on both sides, not about being evasive. If you "
            "need a firm answer, ask for something concrete: a date, an owner, or a yes to a "
            "specific next step."
        ),
        "prompt": (
            'You ask for a deadline and hear "Quite challenging leh". What is the likely meaning?'
        ),
        "explanation": (
            "Softened phrasing usually signals a no. It means the deadline is not realistic, "
            "put in a way that avoids a blunt refusal."
        ),
        "options": [
            ("The deadline is unlikely to be met", True),
            ("They need one more day", False),
            ("They want you to do it instead", False),
            ("They have agreed to the deadline", False),
        ],
    },
    {
        "topic": "Workplace",
        "title": "Lunch, Chat Groups and Belonging",
        "content": (
            "Much of workplace integration happens outside meetings.\n\n"
            "Teams often go for lunch together, and being asked is how inclusion is offered. "
            "Accepting occasionally matters more than accepting every time. Expect the bill "
            "to be split evenly rather than itemised.\n\n"
            "Most teams also run a WhatsApp or Telegram group. It carries real information "
            "alongside the jokes, so being left out of it genuinely leaves you behind. Ask "
            "to be added.\n\n"
            "When ordering for a group, check dietary needs: halal for Muslim colleagues, "
            "vegetarian for some Hindu and Buddhist colleagues."
        ),
        "prompt": "Your team is ordering a shared lunch. What should you check first?",
        "explanation": (
            "Singapore workplaces are religiously mixed, so checking dietary requirements "
            "such as halal and vegetarian is the normal first step."
        ),
        "options": [
            ("Dietary requirements such as halal and vegetarian", True),
            ("Whether everyone can pay in cash", False),
            ("Whether the manager is joining", False),
            ("Whether the restaurant takes reservations", False),
        ],
    },
    # --- Public Etiquette -------------------------------------------------------------
    {
        "topic": "Public Etiquette",
        "title": "Queueing Is Not Optional",
        "content": (
            "Singapore queues, for everything: bus doors, lifts, hawker stalls, taxi stands. "
            "The queue is orderly, single file, and cutting it draws immediate and public "
            "objection.\n\n"
            "A few local details:\n\n"
            "- At MRT doors, markings on the platform show where to stand. Let passengers "
            "off before boarding.\n"
            "- At lifts, people stand aside from the doors rather than crowding them.\n"
            "- A bag or umbrella on the floor can be holding a place in a queue.\n\n"
            "Queue discipline is one of the norms locals notice most quickly in newcomers."
        ),
        "prompt": (
            "The MRT doors open and you are waiting at the platform markings. What comes first?"
        ),
        "explanation": (
            "Passengers leaving the train go first. Boarding before they are off blocks the "
            "doors and is the most commonly criticised breach."
        ),
        "options": [
            ("Let passengers off before boarding", True),
            ("Board quickly to get a seat", False),
            ("Board at the same time, keeping to one side", False),
            ("Wait for staff to signal", False),
        ],
    },
    {
        "topic": "Public Etiquette",
        "title": "On the MRT and Buses",
        "content": (
            "Public transport carries its own rules, some of them enforced by fine.\n\n"
            "- **No eating or drinking**, water included, anywhere inside stations or "
            "carriages.\n"
            "- **No durians**, which is a real and famously signposted rule.\n"
            "- Reserved seats, marked in a different colour, are for elderly passengers, "
            "pregnant passengers, passengers with injuries and those with young children. "
            "You may sit in one, but give it up when someone needs it.\n"
            "- Keep calls quiet and use earphones.\n\n"
            "Backpacks come off in crowded carriages and are carried at your side."
        ),
        "prompt": (
            "You are sitting in a reserved seat and someone who needs it boards. What is expected?"
        ),
        "explanation": (
            "Reserved seats may be used when free, but the expectation is that you give the "
            "seat up as soon as someone who needs it boards."
        ),
        "options": [
            ("Give up the seat", True),
            ("Stay seated, since you boarded first", False),
            ("Wait to be asked", False),
            ("Move to a different reserved seat", False),
        ],
    },
    {
        "topic": "Public Etiquette",
        "title": "Living Close to Your Neighbours",
        "content": (
            "About eight in ten residents live in HDB flats, so noise and shared space "
            "matter.\n\n"
            "- Keep drilling and heavy work to daytime hours, typically 9am to 5pm on "
            "weekdays, and avoid Sundays and public holidays.\n"
            "- Corridors are shared and must stay clear: they are fire escape routes, and "
            "blocking them draws a warning from the town council.\n"
            '- Never throw anything from a window or balcony. "Killer litter" is treated '
            "as a serious offence, not a nuisance.\n\n"
            "Disputes usually go to the town council or the Community Mediation Centre "
            "rather than the police."
        ),
        "prompt": "Where do neighbour disputes in HDB blocks usually go first?",
        "explanation": (
            "The town council or the Community Mediation Centre handles most neighbour "
            "disputes; the police are not the usual first step."
        ),
        "options": [
            ("The town council or Community Mediation Centre", True),
            ("The police", False),
            ("The Housing and Development Board directly", False),
            ("A civil court claim", False),
        ],
    },
    # --- Festivals --------------------------------------------------------------------
    {
        "topic": "Festivals",
        "title": "Chinese New Year",
        "content": (
            "Two public holidays in January or February, and the busiest family period of "
            "the year.\n\n"
            "- **Ang bao** are red packets of money, given by married people to children and "
            "to unmarried younger adults. Notes should be new, and the amount even; avoid "
            'anything with a four in it, as the word sounds like "death".\n'
            "- Visiting relatives runs over several days. If invited, bring mandarin oranges, "
            "traditionally in pairs.\n"
            "- **Lo hei**, a tossed raw fish salad, is shared at work and family meals. "
            "Everyone tosses together, the higher the better.\n\n"
            "Red and gold are auspicious; avoid giving anything in white or black wrapping."
        ),
        "prompt": (
            "You are invited to a colleague's home for Chinese New Year. What is a suitable gift?"
        ),
        "explanation": (
            "A pair of mandarin oranges is the traditional gift when visiting during Chinese "
            "New Year."
        ),
        "options": [
            ("A pair of mandarin oranges", True),
            ("A set of four pastries", False),
            ("A gift wrapped in white paper", False),
            ("A clock or watch", False),
        ],
    },
    {
        "topic": "Festivals",
        "title": "Hari Raya Puasa",
        "content": (
            "Hari Raya Puasa marks the end of Ramadan, the month when Muslims fast from dawn "
            "to sunset.\n\n"
            "During Ramadan, be considerate about eating in front of fasting colleagues, and "
            "expect meeting times to shift around **iftar**, the evening meal that breaks the "
            "fast. Geylang Serai fills with a night bazaar.\n\n"
            "On Hari Raya itself, families hold open houses and guests are genuinely welcome. "
            "Dress modestly, remove your shoes at the door, and accept food with your right "
            'hand. The greeting is *"Selamat Hari Raya"*, often with *"Maaf zahir dan '
            'batin"*, asking forgiveness for any wrong done.'
        ),
        "prompt": (
            "You are visiting a colleague's open house on Hari Raya. "
            "What should you do at the door?"
        ),
        "explanation": (
            "Shoes come off at the door in Malay and Muslim homes, and modest dress is "
            "expected when visiting."
        ),
        "options": [
            ("Remove your shoes before entering", True),
            ("Wait to be served before sitting", False),
            ("Bring alcohol as a gift", False),
            ("Greet the eldest person with a handshake", False),
        ],
    },
    {
        "topic": "Festivals",
        "title": "Deepavali",
        "content": (
            "Deepavali, the festival of lights, marks the triumph of light over darkness and "
            "falls in October or November.\n\n"
            "Little India is lit up for weeks beforehand and is worth seeing in the evening. "
            "Homes are cleaned, decorated with **kolam** patterns at the entrance, and opened "
            "to visitors.\n\n"
            "If invited, dress brightly rather than in black or white, and bring sweets or "
            "fruit. Many Hindu households are vegetarian, so avoid gifts containing meat, and "
            'avoid leather. The greeting is *"Happy Deepavali"*.\n\n'
            "As with other festivals here, invitations from colleagues are sincere."
        ),
        "prompt": "What is a suitable gift when invited to a Hindu colleague's home for Deepavali?",
        "explanation": (
            "Sweets or fruit suit the occasion. Many Hindu households are vegetarian, so "
            "meat-based gifts and leather items are avoided."
        ),
        "options": [
            ("Sweets or fruit", True),
            ("A leather wallet", False),
            ("A meat hamper", False),
            ("Something wrapped in black", False),
        ],
    },
    # --- Getting Around ---------------------------------------------------------------
    {
        "topic": "Getting Around",
        "title": "Paying for Public Transport",
        "content": (
            "You do not need a separate transport card. Most people tap a contactless bank "
            "card or a phone wallet directly on the reader, through **SimplyGo**.\n\n"
            "The alternatives are an **EZ-Link** or **NETS FlashPay** stored-value card, "
            "sold at station counters and convenience stores, which suit anyone who prefers "
            "not to link a bank card.\n\n"
            "Tap in when you board and **tap out when you leave**, on buses as well as trains. "
            "Fares are distance-based across the whole journey, so transfers within a trip "
            "cost less than separate journeys. Forgetting to tap out charges you the maximum "
            "fare for that line."
        ),
        "prompt": "What happens if you forget to tap out when leaving a bus or train?",
        "explanation": (
            "Fares are distance-based and calculated between your tap in and tap out, so "
            "missing the tap out charges the maximum fare for that line."
        ),
        "options": [
            ("You are charged the maximum fare for that line", True),
            ("You are charged nothing for the trip", False),
            ("Your card is blocked until you visit a counter", False),
            ("You are charged a flat minimum fare", False),
        ],
    },
    {
        "topic": "Getting Around",
        "title": "Catching a Bus",
        "content": (
            "Buses do not stop automatically. At the stop, **put your hand out** as your bus "
            "approaches, or it will drive past. Inside, press the bell once, well before your "
            "stop.\n\n"
            "Board at the front, alight at the middle doors where there are two. Tap your "
            "card at both.\n\n"
            "Bus numbers with an **e** suffix are express and skip stops; check the route "
            "before boarding. Apps such as the official MyTransport.SG, or Google Maps, give "
            "live arrival times, and most stops display them on a panel or a QR code."
        ),
        "prompt": "Your bus is approaching the stop. What do you need to do?",
        "explanation": (
            "Singapore buses stop on request. Putting your hand out signals the driver; "
            "without it the bus may drive past."
        ),
        "options": [
            ("Put your hand out to signal the driver", True),
            ("Stand at the front of the queue and wait", False),
            ("Press the bell at the stop", False),
            ("Nothing, every bus stops at every stop", False),
        ],
    },
    {
        "topic": "Getting Around",
        "title": "Taxis and Ride-Hailing",
        "content": (
            "Grab, Gojek and TADA cover most private-hire trips and quote a fixed fare up "
            "front. Street taxis such as ComfortDelGro run on the meter, and can be flagged "
            "down anywhere it is safe to stop, except along roads with double yellow lines "
            "or inside the CBD during restricted hours, where you use a taxi stand.\n\n"
            "Expect surcharges: peak hours, late night, airport pickups, and trips out of the "
            "city centre in the morning. They are added automatically and are not negotiable."
            "\n\nTipping is not customary, and drivers may decline it.\n\n"
            "Seatbelts are required in the back seat as well as the front."
        ),
        "prompt": "What is the norm on tipping taxi and ride-hailing drivers in Singapore?",
        "explanation": (
            "Tipping is not customary in Singapore. The metered or quoted fare, plus any "
            "automatic surcharges, is the full amount."
        ),
        "options": [
            ("Tipping is not customary", True),
            ("Ten per cent is expected", False),
            ("Round up to the nearest five dollars", False),
            ("Tip only on airport trips", False),
        ],
    },
]

# How many of each topic's lessons the demo Newcomer has finished, so the landing page
# shows every state a circle can be in: not started, in progress and complete
# (SCRUM-43 AC3, AC4, AC5). Only applied when the account has no progress at all.
SEEDED_COMPLETIONS = {
    "Singlish": 2,
    "Hawker & Food": 0,
    "Workplace": 1,
    "Public Etiquette": 3,
    "Festivals": 1,
    "Getting Around": 2,
}


def _get_or_create_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    role: UserRole,
    user_type: UserType | None,
) -> tuple[User, bool]:
    email = normalise_email(email)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        user_type=user_type,
    )
    db.add(user)
    return user, True


def _create_lesson(spec: dict, topic: Topic, position: int) -> Lesson:
    lesson = Lesson(
        title=spec["title"],
        content=spec["content"],
        topic=topic,
        position=position,
        status=LessonStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )
    lesson.question = QuizQuestion(
        prompt=spec["prompt"],
        explanation=spec["explanation"],
        options=[
            QuizOption(text=text, is_correct=correct, position=position)
            for position, (text, correct) in enumerate(spec["options"])
        ],
    )
    return lesson


def _seed_completions(db: Session, user: User) -> list[str]:
    """Give the demo account some progress, but never overwrite real progress."""
    if db.scalar(
        select(func.count())
        .select_from(LessonCompletion)
        .where(LessonCompletion.user_id == user.id)
    ):
        return []

    log: list[str] = []
    for topic_name, count in SEEDED_COMPLETIONS.items():
        if count == 0:
            continue
        lessons = db.scalars(
            select(Lesson)
            .join(Topic)
            .where(Topic.name == topic_name, Lesson.status == LessonStatus.PUBLISHED)
            .order_by(Lesson.title)
            .limit(count)
        ).all()
        for index, lesson in enumerate(lessons):
            # Alternate right and wrong, so the stored correctness is not uniformly true
            # once tiers (SCRUM-27) start reading it.
            db.add(
                LessonCompletion(
                    user_id=user.id, lesson_id=lesson.id, answered_correctly=index % 2 == 0
                )
            )
        if lessons:
            log.append(f"{len(lessons)} completed lesson(s) in {topic_name}")
    return log


def seed(db: Session) -> list[str]:
    """Insert anything missing and return a short log of what was created."""
    settings = get_settings()
    log: list[str] = []

    admin, created = _get_or_create_user(
        db,
        settings.seed_admin_email,
        settings.seed_admin_password,
        "SGJio Admin",
        UserRole.ADMIN,
        None,
    )
    if created:
        log.append(f"admin account {admin.email}")

    user, created = _get_or_create_user(
        db,
        settings.seed_user_email,
        settings.seed_user_password,
        "Siddharth Sharma",
        UserRole.USER,
        UserType.NEWCOMER,
    )
    if created:
        user.profile = Profile(
            neighbourhood="Tampines",
            interests=["Food", "Football"],
            languages=["English", "Hindi"],
        )
        log.append(f"user account {user.email}")

    topics: dict[str, Topic] = {}
    next_position = next_topic_position(db)
    for name in TOPICS:
        topic = db.scalar(select(Topic).where(func.lower(Topic.name) == name.lower()))
        if topic is None:
            topic = Topic(name=name, position=next_position)
            next_position += 1
            db.add(topic)
            log.append(f"topic {name}")
        topics[name] = topic
    db.flush()

    added = 0
    next_lesson: dict[str, int] = {}
    for spec in LESSONS:
        if db.scalar(select(Lesson).where(Lesson.title == spec["title"])) is None:
            topic = topics[spec["topic"]]
            if spec["topic"] not in next_lesson:
                next_lesson[spec["topic"]] = next_lesson_position(db, topic.id)
            db.add(_create_lesson(spec, topic, next_lesson[spec["topic"]]))
            next_lesson[spec["topic"]] += 1
            added += 1
    if added:
        log.append(f"{added} published lesson(s) with quizzes")
    db.flush()

    log.extend(_seed_completions(db, user))

    db.commit()
    return log
