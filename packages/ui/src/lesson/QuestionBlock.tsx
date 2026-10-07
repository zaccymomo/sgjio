import { Check, X } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { LessonText } from "./LessonText";
import type { AnswerState } from "./answer";
import type { LearnerQuestion } from "./types";

const tile =
  "inline-flex min-h-11 items-center justify-center rounded-xl border-2 px-4 py-2 text-[17px] font-semibold leading-tight select-none";

function textOf(question: LearnerQuestion, id: string | null | undefined): string {
  return question.options.find((option) => option.id === id)?.text ?? "";
}

/** What the slot in the text shows: the chosen tile, or after checking, the right answer. */
function slotOption(answer: AnswerState): string | null {
  if (answer.status !== "done" || !answer.result) return answer.selected;
  if (answer.result.correct || answer.revealed) return answer.result.correct_option_id;
  return answer.selected;
}

/**
 * The blank in a card's text. Empty, it is a dashed slot that gently pulses; filled, it holds
 * the chosen tile, which flies in from the options below (a shared layout animation keyed on
 * the option). Selecting a filled slot sends the tile back.
 */
export function BlankSlot({
  question,
  answer,
  onClear,
}: {
  question: LearnerQuestion;
  answer: AnswerState;
  onClear: () => void;
}) {
  const reduced = useReducedMotion();
  const optionId = slotOption(answer);
  const done = answer.status === "done" && answer.result;
  const right = done && (answer.result!.correct || answer.revealed);
  const wrong = done && !answer.result!.correct && !answer.revealed;

  if (!optionId) {
    return (
      <motion.span
        aria-label="Blank"
        className="mx-0.5 inline-block h-[1.35em] w-20 translate-y-[0.28em] rounded-lg border-2 border-dashed border-brand/60 bg-brand-soft"
        animate={reduced ? undefined : { opacity: [1, 0.55, 1] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }
  return (
    <motion.button
      type="button"
      layoutId={`option-${optionId}`}
      onClick={answer.status === "idle" ? onClear : undefined}
      disabled={answer.status !== "idle"}
      aria-label={`Your answer: ${textOf(question, optionId)}${answer.status === "idle" ? ". Select to remove it" : ""}`}
      className={cn(
        tile,
        "mx-0.5 translate-y-[0.1em] align-baseline",
        !done && "border-ink bg-white text-ink shadow-[0_2px_0_0_var(--color-ink)]",
        right && "border-success bg-success-soft text-success",
        wrong && "border-danger bg-danger-soft text-danger",
      )}
      animate={
        reduced
          ? undefined
          : wrong
            ? { x: [0, -10, 10, -7, 7, -3, 0] }
            : right
              ? { scale: [1, 1.12, 1] }
              : { x: 0, scale: 1 }
      }
      transition={{ layout: { type: "spring", stiffness: 520, damping: 34 }, duration: 0.45 }}
    >
      {right && <Check className="mr-1.5 size-4" strokeWidth={3} aria-hidden />}
      {textOf(question, optionId)}
    </motion.button>
  );
}

/**
 * The options for a blank, as tiles. A tile in the slot leaves a ghost of its size behind, so
 * nothing jumps. After a wrong answer the chosen tile comes back struck through.
 */
export function TileBank({
  question,
  answer,
  onSelect,
}: {
  question: LearnerQuestion;
  answer: AnswerState;
  onSelect: (optionId: string) => void;
}) {
  const inSlot = slotOption(answer);
  const done = answer.status === "done" && answer.result;
  // A finished one-option tap has nothing left to show below the text.
  if (done && !question.scored) return null;
  return (
    <div className="flex flex-wrap justify-center gap-2.5" role="group" aria-label="Options">
      {question.options.map((option, n) => {
        if (option.id === inSlot) {
          return (
            <span
              key={option.id}
              className={cn(tile, "border-dashed border-line bg-surface")}
              aria-hidden
            >
              <span className="invisible">{option.text}</span>
            </span>
          );
        }
        const picked = done && option.id === answer.selected && !answer.result!.correct;
        return (
          <motion.button
            key={option.id}
            type="button"
            layoutId={`option-${option.id}`}
            onClick={() => onSelect(option.id)}
            disabled={answer.status !== "idle"}
            aria-keyshortcuts={String(n + 1)}
            className={cn(
              tile,
              "border-line bg-white text-ink shadow-[0_2px_0_0_var(--color-line)] transition-colors hover:border-ink/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-default",
              picked && "border-danger/50 bg-danger-soft text-danger line-through decoration-2",
              done && !picked && "opacity-45",
            )}
            whileTap={answer.status === "idle" ? { scale: 0.94 } : undefined}
            transition={{ layout: { type: "spring", stiffness: 520, damping: 34 } }}
          >
            {picked && <X className="mr-1.5 size-4" strokeWidth={3} aria-hidden />}
            {option.text}
          </motion.button>
        );
      })}
    </div>
  );
}

/** The options for a question without a blank: full-width answer cards. */
export function AnswerList({
  question,
  answer,
  onSelect,
}: {
  question: LearnerQuestion;
  answer: AnswerState;
  onSelect: (optionId: string) => void;
}) {
  const reduced = useReducedMotion();
  const done = answer.status === "done" && answer.result;
  return (
    <div className="flex flex-col gap-2.5" role="radiogroup" aria-label="Options">
      {question.options.map((option, n) => {
        const selected = answer.selected === option.id;
        const isRight = done && option.id === answer.result!.correct_option_id;
        const isWrongPick = done && selected && !answer.result!.correct;
        return (
          <motion.button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-keyshortcuts={String(n + 1)}
            onClick={() => onSelect(option.id)}
            disabled={answer.status !== "idle"}
            className={cn(
              "flex min-h-14 w-full items-center gap-3 rounded-2xl border-2 px-4 py-3 text-left text-[16px] leading-snug font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-default",
              !done && !selected && "border-line bg-white text-ink hover:border-ink/40",
              !done &&
                selected &&
                "border-ink bg-white text-ink shadow-[0_3px_0_0_var(--color-ink)]",
              isRight && "border-success bg-success-soft text-success",
              isWrongPick && "border-danger bg-danger-soft text-danger",
              done && !isRight && !isWrongPick && "border-line bg-white text-muted opacity-60",
            )}
            whileTap={answer.status === "idle" ? { scale: 0.98 } : undefined}
            animate={
              reduced
                ? undefined
                : isWrongPick
                  ? { x: [0, -8, 8, -5, 5, 0] }
                  : isRight
                    ? { scale: [1, 1.03, 1] }
                    : {}
            }
            transition={{ duration: 0.4 }}
          >
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-lg border-2 text-xs font-bold",
                isRight
                  ? "border-success bg-success text-white"
                  : isWrongPick
                    ? "border-danger bg-danger text-white"
                    : selected
                      ? "border-ink bg-ink text-white"
                      : "border-line text-muted",
              )}
              aria-hidden
            >
              {isRight ? (
                <Check className="size-4" strokeWidth={3} />
              ) : isWrongPick ? (
                <X className="size-4" strokeWidth={3} />
              ) : (
                n + 1
              )}
            </span>
            {option.text}
          </motion.button>
        );
      })}
    </div>
  );
}

/**
 * What comes up after answering: right or not quite, why the chosen option isn't the norm
 * (when wrong and the lesson says), and the explanation. Never by colour alone: there is
 * always an icon and words.
 */
export function FeedbackSheet({
  question,
  answer,
  action,
}: {
  question: LearnerQuestion;
  answer: AnswerState;
  action: ReactNode;
}) {
  const reduced = useReducedMotion();
  const result = answer.result!;
  const right = result.correct;
  const title = right ? (question.scored ? "That's right!" : "Nice!") : "Not quite";
  return (
    <motion.div
      role="status"
      initial={reduced ? { opacity: 0 } : { y: "100%" }}
      animate={reduced ? { opacity: 1 } : { y: 0 }}
      transition={{ type: "spring", stiffness: 380, damping: 36 }}
      className={cn(
        "flex flex-col gap-3 border-t-2 px-5 pt-4 pb-[max(1.25rem,env(safe-area-inset-bottom))]",
        right ? "border-success/25 bg-success-soft" : "border-danger/20 bg-danger-soft",
      )}
    >
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "flex size-8 items-center justify-center rounded-full text-white",
            right ? "bg-success" : "bg-danger",
          )}
          aria-hidden
        >
          {right ? (
            <Check className="size-5" strokeWidth={3} />
          ) : (
            <X className="size-5" strokeWidth={3} />
          )}
        </span>
        <p className={cn("text-lg font-bold", right ? "text-success" : "text-danger")}>{title}</p>
      </div>
      <div className="max-h-40 overflow-y-auto text-[15px] leading-relaxed text-ink">
        {!right && (
          <p className="mb-2">
            The answer is{" "}
            <strong className="font-semibold">{textOf(question, result.correct_option_id)}</strong>.
            {result.why_not && <> {result.why_not}</>}
          </p>
        )}
        {result.explanation && <LessonText text={result.explanation} />}
      </div>
      {action}
    </motion.div>
  );
}
