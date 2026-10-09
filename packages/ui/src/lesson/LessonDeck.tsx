import confetti from "canvas-confetti";
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  HelpCircle,
  Layers,
  RotateCcw,
  Sparkles,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion, type PanInfo } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { cn } from "../lib/cn";
import { BLANK_PATTERN, hasBlank, readingLabel } from "./doc";
import { LessonText } from "./LessonText";
import { NO_ANSWER, type AnswerState } from "./answer";
import { AudioPlayer, CardImage } from "./media";
import { tint } from "./tint";
import { AnswerList, BlankSlot, FeedbackSheet, TileBank } from "./QuestionBlock";
import { playCorrect, playFanfare, playTick, playWrong, useMuted, vibrate } from "./sound";
import type { Assets, CheckAnswer, LearnerCard, LearnerQuestion } from "./types";

export type DeckLesson = {
  title: string;
  summary?: string;
  topicName?: string | null;
  /** From the lesson's stats: reading time including audio. */
  readingSeconds?: number;
};

export type DeckSummary = {
  /** Questions that count: those with two or more options. */
  scored: number;
  /** Of those, how many were right first time. */
  correct: number;
  /** The scored questions answered wrongly, each as the norm to remember: the card's text
   * with the right answer filled in (Markdown). */
  missed: { questionId: string; remember: string }[];
};

type Props = {
  lesson: DeckLesson;
  cards: LearnerCard[];
  assets: Assets;
  /** Checks an answer: in the browser for a preview, on the server for a learner. */
  check: CheckAnswer;
  /**
   * "full" plays the whole lesson: a cover first, an end card last, autoplaying audio.
   * "embedded" shows one card (`index`) for the editor's live preview, without autoplay.
   */
  variant?: "full" | "embedded";
  index?: number;
  onIndexChange?: (index: number) => void;
  onExit?: () => void;
  /** Shown in the top bar, e.g. a "Preview" label. */
  badge?: ReactNode;
  /** The end card's buttons. Defaults to "Start again" and, with onExit, "Close". */
  renderEnd?: (summary: DeckSummary, restart: () => void) => ReactNode;
  /**
   * Called each time the end card is reached, which needs every question answered. The
   * learner's page records the attempt here; a preview leaves it out, so nothing is saved.
   */
  onFinish?: (summary: DeckSummary) => void;
};

const COVER = -1;

function primaryButton(tone: "ink" | "success" | "danger" = "ink") {
  return cn(
    "flex h-14 w-full items-center justify-center gap-2 rounded-2xl text-base font-bold text-white transition-[transform,background-color] active:translate-y-[2px] disabled:cursor-not-allowed disabled:bg-line disabled:text-subtle disabled:shadow-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
    tone === "ink" && "bg-ink shadow-[0_3px_0_0_#000] hover:bg-ink/90",
    tone === "success" && "bg-success shadow-[0_3px_0_0_#15803d] hover:bg-success/90",
    tone === "danger" && "bg-danger shadow-[0_3px_0_0_#b91c1c] hover:bg-danger/90",
  );
}

/**
 * A lesson as a deck of cards (SCRUM-19, SCRUM-65): the one component learners use and the
 * admin portal previews with, so a preview is exactly what learners see.
 *
 * It lays itself out by the width of what it is placed in, not the screen: in a phone-width
 * space it fills it; given more room it becomes a portrait card on a backdrop made from the
 * current card's image. Give it a definite height.
 *
 * Moving on: the Continue button, swiping, or ←/→. A question must be answered before moving
 * past it; Enter checks, and 1–4 pick an option. Nothing ever moves on by itself.
 */
export function LessonDeck({
  lesson,
  cards,
  assets,
  check,
  variant = "full",
  index,
  onIndexChange,
  onExit,
  badge,
  renderEnd,
  onFinish,
}: Props) {
  const embedded = variant === "embedded";
  const reduced = useReducedMotion();
  const [muted, setMuted] = useMuted();
  const [step, setStep] = useState(embedded ? (index ?? 0) : COVER);
  const [direction, setDirection] = useState(1);
  const [started, setStarted] = useState(false);
  const regionRef = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);

  // Answers are kept with the questions they were given for. An embedded deck follows the
  // editor, so an answer to a question whose options have since changed no longer applies.
  const optionKey = cards
    .map((c) =>
      c.question
        ? `${c.question.id}:${c.question.options.map((o) => o.id + o.text).join(",")}`
        : "",
    )
    .join("|");
  const [answerState, setAnswerState] = useState<{ key: string; map: Record<string, AnswerState> }>(
    { key: optionKey, map: {} },
  );
  const answers = useMemo(
    () => (!embedded || answerState.key === optionKey ? answerState.map : {}),
    [answerState, embedded, optionKey],
  );

  const end = cards.length;
  const current = embedded ? Math.min(Math.max(index ?? 0, 0), Math.max(end - 1, 0)) : step;
  const card = current >= 0 && current < end ? cards[current] : null;
  const question = card?.question ?? null;
  const answer = (question && answers[question.id]) || NO_ANSWER;
  const canAdvance = !question || answer.status === "done";

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const go = useCallback(
    (to: number) => {
      const lowest = embedded ? 0 : COVER;
      const highest = embedded ? end - 1 : end;
      const next = Math.min(Math.max(to, lowest), highest);
      if (next === current) return;
      setDirection(next > current ? 1 : -1);
      if (embedded) onIndexChange?.(next);
      else setStep(next);
    },
    [current, embedded, end, onIndexChange],
  );

  // Moving to a card: put focus on it, so screen readers start there.
  useEffect(() => {
    regionRef.current?.focus({ preventScroll: true });
  }, [current]);

  const summary = useMemo<DeckSummary>(() => {
    const scored = cards.flatMap((c) => (c.question?.scored ? [c.question] : []));
    const missed = cards.flatMap((c) => {
      const q = c.question;
      const result = q?.scored ? answers[q.id]?.result : undefined;
      if (!q || !result || result.correct) return [];
      const answerText = q.options.find((o) => o.id === result.correct_option_id)?.text ?? "";
      const remember = hasBlank(c.text)
        ? c.text.replace(BLANK_PATTERN, `**${answerText}**`)
        : `${c.text}\n\n**${answerText}**`;
      return [{ questionId: q.id, remember }];
    });
    const correct = scored.filter((q) => answers[q.id]?.result?.correct).length;
    return { scored: scored.length, correct, missed };
  }, [answers, cards]);

  function update(questionId: string, change: Partial<AnswerState>) {
    setAnswerState((state) => {
      const map = !embedded || state.key === optionKey ? state.map : {};
      return {
        key: optionKey,
        map: { ...map, [questionId]: { ...(map[questionId] ?? NO_ANSWER), ...change } },
      };
    });
  }

  async function runCheck(q: LearnerQuestion, optionId: string) {
    update(q.id, { status: "checking", selected: optionId, error: undefined });
    try {
      const result = await check(q.id, optionId);
      update(q.id, { status: "done", result });
      if (result.correct) {
        playCorrect();
        vibrate(18);
      } else {
        playWrong();
        vibrate([30, 40, 30]);
        // Let the slot shake first, then move the right answer into it.
        timers.current.push(window.setTimeout(() => update(q.id, { revealed: true }), 650));
      }
    } catch {
      update(q.id, {
        status: "idle",
        error: "We couldn't check your answer. Check your connection and try again.",
      });
    }
  }

  function select(q: LearnerQuestion, optionId: string) {
    if ((answers[q.id] ?? NO_ANSWER).status !== "idle") return;
    playTick();
    update(q.id, { selected: optionId });
    // A one-option tap checks itself once the tile has landed.
    if (!q.scored) timers.current.push(window.setTimeout(() => void runCheck(q, optionId), 380));
  }

  function primary() {
    if (!embedded && current === COVER) {
      setStarted(true);
      return go(0);
    }
    if (current === end) return;
    if (question && answer.status === "idle") {
      if (answer.selected) void runCheck(question, answer.selected);
      return;
    }
    if (canAdvance) go(current + 1);
  }

  function restart() {
    setAnswerState({ key: optionKey, map: {} });
    setDirection(-1);
    setStep(0);
  }

  // Reaching the end card finishes the deck. Read through a ref, so a new callback or
  // summary on a later render doesn't count as finishing again.
  const finishRef = useRef<() => void>(() => {});
  useEffect(() => {
    finishRef.current = () => onFinish?.(summary);
  });
  useEffect(() => {
    if (!embedded && current === end) finishRef.current();
  }, [current, end, embedded]);

  // Confetti and a fanfare when every scored question was right first time.
  const mastered = summary.scored > 0 && summary.correct === summary.scored;
  useEffect(() => {
    if (embedded || current !== end) return;
    if (mastered) {
      playFanfare();
      void confetti({
        particleCount: 120,
        spread: 75,
        origin: { y: 0.35 },
        colors: ["#F43F5E", "#FBBF24", "#34D399", "#60A5FA", "#A78BFA"],
        disableForReducedMotion: true,
      });
    }
  }, [current, end, embedded, mastered]);

  // Keyboard: ←/→ move, Enter checks or continues, 1–4 pick, M mutes, Esc leaves.
  const keyRef = useRef<(event: KeyboardEvent) => void>(() => {});
  const onKey = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
    if (event.key === "ArrowRight") {
      if (current === COVER) primary();
      else if (canAdvance) go(current + 1);
    } else if (event.key === "ArrowLeft") go(current - 1);
    else if (event.key === "Enter" && !(target instanceof HTMLButtonElement)) primary();
    else if (/^[1-4]$/.test(event.key) && question) {
      const option = question.options[Number(event.key) - 1];
      if (option) select(question, option.id);
    } else if (event.key.toLowerCase() === "m") setMuted(!muted);
    else if (event.key === "Escape" && onExit) onExit();
    else return;
    event.preventDefault();
  };
  useEffect(() => {
    keyRef.current = onKey;
  });
  useEffect(() => {
    if (embedded) return;
    const listener = (event: KeyboardEvent) => keyRef.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [embedded]);

  function onSwipe(_: unknown, info: PanInfo) {
    if (info.offset.x < -70 && Math.abs(info.offset.y) < 60) {
      if (current === COVER) primary();
      else if (canAdvance) go(current + 1);
    } else if (info.offset.x > 70 && Math.abs(info.offset.y) < 60) go(current - 1);
  }

  const firstImage = cards.find((c) => c.image)?.image ?? null;
  const backdropAsset = card?.image
    ? assets[card.image.asset_id]
    : firstImage
      ? assets[firstImage.asset_id]
      : undefined;

  const variants = {
    enter: (d: number) => (reduced ? { opacity: 0 } : { x: `${d * 45}%`, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (d: number) => (reduced ? { opacity: 0 } : { x: `${d * -25}%`, opacity: 0 }),
  };

  let bottom: ReactNode;
  if (current === COVER) {
    bottom = (
      <button type="button" className={primaryButton()} onClick={primary}>
        Start lesson
      </button>
    );
  } else if (current === end) {
    bottom = null;
  } else if (question && answer.status === "done" && answer.result) {
    bottom = (
      <FeedbackSheet
        key={question.id}
        question={question}
        answer={answer}
        action={
          <button
            type="button"
            className={primaryButton(answer.result.correct ? "success" : "danger")}
            onClick={() => go(current + 1)}
            disabled={embedded && current >= end - 1}
          >
            Continue
          </button>
        }
      />
    );
  } else if (question) {
    bottom = (
      <div className="flex flex-col gap-2">
        {answer.error && (
          <p role="alert" className="text-center text-sm text-danger">
            {answer.error}
          </p>
        )}
        {question.scored && (
          <button
            type="button"
            className={primaryButton()}
            onClick={primary}
            disabled={!answer.selected || answer.status === "checking"}
          >
            {answer.status === "checking" ? "Checking…" : "Check"}
          </button>
        )}
        {!question.scored && (
          <p className="flex h-14 items-center justify-center text-sm font-medium text-muted">
            Tap the word to fill the blank
          </p>
        )}
      </div>
    );
  } else {
    bottom = (
      <button
        type="button"
        className={primaryButton()}
        onClick={primary}
        disabled={embedded && current >= end - 1}
      >
        Continue
      </button>
    );
  }

  return (
    <div className="@container relative h-full w-full overflow-hidden bg-white">
      {/* Backdrop, only when there is room around the card. */}
      <div
        className="absolute inset-0 hidden @xl:block"
        style={{ background: tint(backdropAsset?.color, 26) }}
        aria-hidden
      >
        {backdropAsset?.placeholder && (
          <img
            src={backdropAsset.placeholder}
            alt=""
            className="h-full w-full scale-125 object-cover opacity-50 blur-3xl transition-opacity duration-700"
          />
        )}
      </div>

      <div className="relative flex h-full items-center justify-center gap-6">
        {!embedded && (
          <button
            type="button"
            onClick={() => go(current - 1)}
            disabled={current === COVER}
            aria-label="Previous card"
            className="hidden size-12 items-center justify-center rounded-full bg-white/80 text-ink shadow-md backdrop-blur transition-opacity hover:bg-white disabled:opacity-0 @xl:flex"
          >
            <ChevronLeft className="size-6" aria-hidden />
          </button>
        )}

        <section
          aria-label={`Lesson: ${lesson.title}`}
          className="relative flex h-full w-full flex-col overflow-hidden bg-white @xl:h-[min(860px,calc(100%-5rem))] @xl:w-[430px] @xl:rounded-[32px] @xl:shadow-[0_30px_80px_-20px_rgb(17_24_39/0.45)]"
        >
          {/* Top bar */}
          <div className="z-10 flex items-center gap-3 px-4 pt-[max(0.875rem,env(safe-area-inset-top))] pb-2">
            {onExit && !embedded && (
              <button
                type="button"
                onClick={onExit}
                aria-label="Close lesson"
                className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
              >
                <X className="size-5" aria-hidden />
              </button>
            )}
            <div className="flex flex-1 gap-1" aria-hidden>
              {cards.map((c, n) => (
                <span key={c.id} className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/10">
                  <motion.span
                    className="block h-full rounded-full bg-brand"
                    initial={false}
                    animate={{ width: n <= current ? "100%" : "0%" }}
                    transition={{ duration: reduced ? 0 : 0.35, ease: "easeOut" }}
                  />
                </span>
              ))}
            </div>
            {badge}
            <button
              type="button"
              onClick={() => setMuted(!muted)}
              aria-label={muted ? "Turn sound on" : "Turn sound off"}
              aria-pressed={muted}
              className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
            >
              {muted ? (
                <VolumeX className="size-5" aria-hidden />
              ) : (
                <Volume2 className="size-5" aria-hidden />
              )}
            </button>
          </div>

          <p className="sr-only" aria-live="polite">
            {current === COVER
              ? `${lesson.title}. Select Start lesson to begin.`
              : current === end
                ? "Lesson complete."
                : `Card ${current + 1} of ${end}`}
          </p>

          {/* Cards */}
          <div className="relative min-h-0 flex-1">
            <AnimatePresence initial={false} custom={direction}>
              <motion.div
                key={current}
                ref={regionRef}
                tabIndex={-1}
                custom={direction}
                variants={variants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{
                  type: "spring",
                  stiffness: 300,
                  damping: 34,
                  opacity: { duration: 0.2 },
                }}
                drag={reduced ? false : "x"}
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={0.18}
                dragSnapToOrigin
                onDragEnd={onSwipe}
                className="absolute inset-0 overflow-y-auto overscroll-contain outline-none"
              >
                {current === COVER ? (
                  <CoverView lesson={lesson} cards={cards} assets={assets} />
                ) : current === end ? (
                  <EndView
                    summary={summary}
                    actions={
                      renderEnd ? (
                        renderEnd(summary, restart)
                      ) : (
                        <>
                          <button type="button" className={primaryButton()} onClick={restart}>
                            <RotateCcw className="size-5" aria-hidden />
                            Start again
                          </button>
                          {onExit && (
                            <button
                              type="button"
                              onClick={onExit}
                              className="h-12 w-full rounded-2xl text-base font-semibold text-muted hover:bg-ink/5 hover:text-ink"
                            >
                              Close
                            </button>
                          )}
                        </>
                      )
                    }
                  />
                ) : card ? (
                  <LayoutGroup id={card.id}>
                    <CardView
                      card={card}
                      assets={assets}
                      answer={answer}
                      autoplay={!embedded && started}
                      direction={direction}
                      onSelect={(optionId) => question && select(question, optionId)}
                      onClear={() => question && update(question.id, { selected: null })}
                    />
                  </LayoutGroup>
                ) : (
                  <p className="p-8 text-center text-sm text-muted">
                    This lesson has no cards yet.
                  </p>
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          {bottom !== null && (
            <div
              className={cn(
                "z-10",
                !(question && answer.status === "done") &&
                  "px-5 pt-3 pb-[max(1.25rem,env(safe-area-inset-bottom))]",
              )}
            >
              {bottom}
            </div>
          )}
        </section>

        {!embedded && (
          <button
            type="button"
            onClick={() => (current === COVER ? primary() : go(current + 1))}
            disabled={current === end || (current !== COVER && !canAdvance)}
            aria-label="Next card"
            className="hidden size-12 items-center justify-center rounded-full bg-white/80 text-ink shadow-md backdrop-blur transition-opacity hover:bg-white disabled:opacity-0 @xl:flex"
          >
            <ChevronRight className="size-6" aria-hidden />
          </button>
        )}
      </div>

      {!embedded && (
        <p
          className="pointer-events-none absolute inset-x-0 bottom-3 hidden text-center text-xs text-ink/50 @xl:block"
          aria-hidden
        >
          ← → to move · Enter to check · 1–4 to choose · M to mute
        </p>
      )}
    </div>
  );
}

// --- The cards -----------------------------------------------------------------------------

function CardView({
  card,
  assets,
  answer,
  autoplay,
  direction,
  onSelect,
  onClear,
}: {
  card: LearnerCard;
  assets: Assets;
  answer: AnswerState;
  autoplay: boolean;
  direction: number;
  onSelect: (optionId: string) => void;
  onClear: () => void;
}) {
  const reduced = useReducedMotion();
  const image = card.image ? assets[card.image.asset_id] : undefined;
  const audio = card.audio ? assets[card.audio.asset_id] : undefined;
  const question = card.question;
  const blank = question !== null && hasBlank(card.text);
  // A short text-only card becomes a statement: big type on a soft tint. Longer ones, and
  // lists, read better at the usual size.
  const short =
    card.text.trim().split(/\s+/).length <= 32 && !/^\s*([-*+]|\d+[.)])\s/m.test(card.text);
  const statement = !card.image && !card.audio && !question && short;

  // The media drifts a little less than the text: a hint of depth as cards slide.
  const media = (children: ReactNode) => (
    <motion.div
      initial={reduced ? false : { x: `${direction * -12}%` }}
      animate={{ x: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 32 }}
      className="relative overflow-hidden rounded-3xl"
    >
      {children}
    </motion.div>
  );

  if (statement) {
    return (
      <div className="flex min-h-full items-center px-5 py-6">
        <div className="w-full rounded-3xl bg-[linear-gradient(160deg,var(--color-brand-soft),#fff7ed)] px-6 py-10">
          <LessonText
            text={card.text}
            className="text-[24px] leading-snug font-semibold text-ink"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-5 px-5 pt-2 pb-6">
      {card.image &&
        media(
          <>
            <CardImage asset={image} alt={card.image.alt} />
            {card.audio && (
              <div className="absolute inset-x-3 bottom-3">
                <AudioPlayer
                  asset={audio}
                  transcript={card.audio.transcript}
                  autoplay={autoplay}
                  size="pill"
                />
              </div>
            )}
          </>,
        )}
      {!card.image &&
        card.audio &&
        media(
          <AudioPlayer
            asset={audio}
            transcript={card.audio.transcript}
            autoplay={autoplay}
            size="large"
          />,
        )}

      <LessonText
        text={card.text}
        className={cn("text-[19px] leading-relaxed text-ink", question && "font-medium")}
        renderBlank={
          blank && question
            ? () => <BlankSlot question={question} answer={answer} onClear={onClear} />
            : undefined
        }
      />

      {question && (
        <div className={cn("pt-3", blank && "pt-8")}>
          {blank ? (
            <TileBank question={question} answer={answer} onSelect={onSelect} />
          ) : (
            <AnswerList question={question} answer={answer} onSelect={onSelect} />
          )}
        </div>
      )}
    </div>
  );
}

function CoverView({
  lesson,
  cards,
  assets,
}: {
  lesson: DeckLesson;
  cards: LearnerCard[];
  assets: Assets;
}) {
  const first = cards.find((c) => c.image)?.image;
  const questions = cards.filter((c) => c.question?.scored).length;
  const meta = [
    { icon: Layers, label: `${cards.length} ${cards.length === 1 ? "card" : "cards"}` },
    { icon: HelpCircle, label: `${questions} ${questions === 1 ? "question" : "questions"}` },
    ...(lesson.readingSeconds !== undefined
      ? [{ icon: Clock, label: readingLabel(lesson.readingSeconds) }]
      : []),
  ];
  const image = first ? assets[first.asset_id] : undefined;
  return (
    <div className="flex min-h-full flex-col" style={{ background: tint(image?.color, 32) }}>
      {/* A title screen rather than a first card: the image large on its own colour, with
          the lesson's details on a sheet rising from the bottom. */}
      <div className="flex flex-1 items-center justify-center px-7 pt-3 pb-12">
        {first ? (
          <motion.div
            initial={{ scale: 0.9, opacity: 0, rotate: -2 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 18, delay: 0.1 }}
            className="w-full overflow-hidden rounded-[28px] shadow-[0_20px_40px_-18px_rgb(17_24_39/0.45)]"
          >
            <CardImage asset={image} alt={first.alt} />
          </motion.div>
        ) : (
          <Sparkles className="size-20 text-brand" aria-hidden />
        )}
      </div>
      <div className="-mt-6 flex flex-col gap-4 rounded-t-[28px] bg-white px-5 pt-6 pb-4">
        <div className="flex flex-col gap-2.5">
          {lesson.topicName && (
            <span className="w-fit rounded-full bg-brand-soft px-3 py-1 text-xs font-bold tracking-wide text-brand uppercase">
              {lesson.topicName}
            </span>
          )}
          <h2 className="text-[28px] leading-tight font-bold text-balance text-ink">
            {lesson.title || "Untitled lesson"}
          </h2>
          {lesson.summary && (
            <p className="text-base leading-relaxed text-muted">{lesson.summary}</p>
          )}
        </div>
        <ul className="flex flex-wrap gap-2">
          {meta.map(({ icon: Icon, label }) => (
            <li
              key={label}
              className="flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-xs font-medium text-muted"
            >
              <Icon className="size-3.5" aria-hidden />
              {label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ScoreRing({ correct, total }: { correct: number; total: number }) {
  const reduced = useReducedMotion();
  const share = total ? correct / total : 1;
  const radius = 62;
  return (
    <div className="relative size-40">
      <svg viewBox="0 0 160 160" className="size-full -rotate-90" aria-hidden>
        <circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth="14"
        />
        <motion.circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke={share === 1 ? "var(--color-success)" : "var(--color-brand)"}
          strokeWidth="14"
          strokeLinecap="round"
          initial={{ pathLength: reduced ? share : 0 }}
          animate={{ pathLength: share }}
          transition={{ duration: 1.1, ease: "easeOut", delay: 0.25 }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-bold text-ink tabular-nums">
          {correct}
          <span className="text-2xl text-subtle">/{total}</span>
        </span>
        <span className="text-xs font-medium text-muted">first time</span>
      </div>
    </div>
  );
}

function EndView({ summary, actions }: { summary: DeckSummary; actions: ReactNode }) {
  const reduced = useReducedMotion();
  const mastered = summary.scored > 0 && summary.correct === summary.scored;
  const heading =
    summary.scored === 0 ? "Lesson complete" : mastered ? "Mastered!" : "Lesson complete";
  const line =
    summary.scored === 0
      ? "Nicely done. There was nothing to score this time."
      : mastered
        ? "Every question right first time."
        : `You got ${summary.correct} of ${summary.scored} right first time. Retake it any time.`;
  return (
    <div className="flex min-h-full flex-col items-center gap-5 px-6 pt-8 pb-6 text-center">
      <motion.div
        initial={reduced ? false : { scale: 0.7, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
      >
        {summary.scored > 0 ? (
          <ScoreRing correct={summary.correct} total={summary.scored} />
        ) : (
          <div className="flex size-40 items-center justify-center rounded-full bg-success-soft">
            <Sparkles className="size-16 text-success" aria-hidden />
          </div>
        )}
      </motion.div>
      <div className="flex flex-col gap-1.5">
        <h2 className="text-[28px] font-bold text-ink">{heading}</h2>
        <p className="text-base text-muted">{line}</p>
      </div>
      {summary.missed.length > 0 && (
        <div className="w-full rounded-2xl bg-surface p-4 text-left">
          <p className="mb-2 text-xs font-bold tracking-wide text-muted uppercase">
            Worth remembering
          </p>
          <ul className="flex flex-col gap-3 text-[15px] leading-relaxed text-ink">
            {summary.missed.map((miss) => (
              <li key={miss.questionId} className="flex gap-2.5">
                <span className="mt-0.5 font-bold text-success" aria-hidden>
                  ✓
                </span>
                <LessonText text={miss.remember} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-auto flex w-full flex-col gap-2">{actions}</div>
    </div>
  );
}
