# Lesson content

The lessons SGJio starts with, written as files so they can be added and changed without the admin portal. The seed loads them, and so can this command:

```bash
cd api && python -m app.cli import-lessons --publish    # loads content/lessons
python -m app.cli import-lessons ../somewhere/else       # or another folder; without --publish they stay drafts
```

Running it again is safe. Unchanged files change nothing, changed files update the lesson (and, with `--publish`, publish a new version), and nobody's progress is touched. Lessons are matched by their **key**, which is their folder path without number prefixes: `lessons/02-hawker-food/01-ordering-kopi` is `hawker-food/ordering-kopi`.

To share a lesson you built in the admin portal, copy its text into a file here. Everyone else then gets it with `python -m app.cli seed`.

## A lesson folder

```
lessons/02-hawker-food/01-ordering-kopi/
  lesson.yaml          the lesson
  cover.png            images its cards use (JPEG, PNG or WebP; 4:3 looks best)
  kopi-o-kosong.mp3    audio its cards use (MP3, M4A, WAV or Ogg; keep it under 20 seconds)
```

Number prefixes set the order new lessons take in their topic. After that, the order is whatever administrators set in the portal; files never move a lesson.

## lesson.yaml

```yaml
title: Ordering at a Local Hawker Centre
summary: Chope a seat first, then order your kopi in code. # one line, up to 160 characters
topic: Hawker & Food # created at the end if it doesn't exist yet
level: 1 # 1 to 5 (see below); left out, a new lesson is Level 1
# publish: false            # keep it a draft, e.g. for a lesson still being written
cards:
  - image: { file: cover.png, alt: "Two cups of kopi on a marble kopitiam table" }
    text: |-
      At a busy hawker centre, find a seat **before** you queue.

  - audio: { file: kopi-o-kosong.mp3, transcript: "Uncle, one kopi-o kosong." }
    text: |-
      Put them together and you get orders like this one.

  - text: |-
      Black coffee **with** sugar is kopi {{blank}}.
    question:
      options:
        - text: "O"
          correct: true
        - text: "C"
          why_not: "C means evaporated milk, so it still has milk."
        - text: "kosong"
          why_not: "Kosong means no sugar, and you want sugar."
      explanation: |-
        **O** takes the milk out and keeps the sugar.
      # shuffle: false          # keep the options in this order (they are shuffled by default)
```

Each card has **text**, and may have an **image**, **audio** or both, and a **question**.

- **Text** is Markdown: `**bold**`, `*italic*` (use it for Singlish and Malay words), and lists. Keep each card under about 50 words, and the whole lesson under 2 minutes to read.
- **A blank**, written `{{blank}}`, is filled by the card's question. One per card at most.
- **A question** has 1 to 4 options and an `explanation` shown after answering. A scored question needs at least 2 distinct options with exactly one marked `correct: true`; every published lesson needs at least one scored question. A question with a single option needs no marking: it's a tap that keeps learners doing something, and isn't scored. Without a blank, the options are shown below the text.
- **`why_not`** on a wrong option is shown when a learner picks it: why it isn't the norm. Worth writing for the tempting ones.
- **Images** need `alt` text describing them, and **audio** a `transcript`.
- **`level`** is how advanced the lesson is, from 1 (essentials for your first weeks) to 5 (insider knowledge); the admin portal describes each one. The aptitude quiz exempts learners from a topic's lessons up to the level they reach there. A file can change a lesson's level only until it is first published; after that it is fixed, and the import says so if the file disagrees.
- **Put text in quotes** when it is on the same line as its name, as above. Without them, a comma or a colon in the text ends it early, and the import says something is wrong. Multi-line text after `|-` needs no quotes.

Every lesson needs a title, a topic and at least one question to be published. The import tells you what is missing, and `api/tests/test_content_import.py` checks every lesson here loads and is ready.

## Aptitude question bank

`aptitude_questions.yaml` is the separate, version-controlled onboarding question bank.
Each question has a stable `key`, a topic, a level from 1 to 5, answer options and exactly
one `correct: true` option. The stable key means editing the file and running the seed again
updates the same row instead of creating a duplicate.

## The images and audio here

The illustrations are placeholders drawn to one flat style, and the audio was made with Singapore-English text-to-speech voices. Replace them freely; [STYLE.md](STYLE.md) says how to keep new ones looking like they belong together.
