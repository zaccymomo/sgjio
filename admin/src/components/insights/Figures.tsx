import { cn } from "@sgjio/ui";
import { LessonText } from "@sgjio/ui/lesson";
import { Check, Eye } from "lucide-react";

import { percent, type InsightsQuestion, type LessonInsights } from "../../lib/insights";

/** Right-first-time bands: 75% and up works, under half needs rewriting. */
type Band = "good" | "fair" | "poor";

function band(share: number): Band {
  return share >= 0.75 ? "good" : share >= 0.5 ? "fair" : "poor";
}

const BAND_FILL: Record<Band, string> = {
  good: "bg-success",
  fair: "bg-amber-500",
  poor: "bg-danger",
};

/** "▲ 12 pts on version 1", or nothing when there is no earlier figure. */
export function Change({
  now,
  before,
  version,
}: {
  now: number | null;
  before: number | null | undefined;
  version?: number;
}) {
  if (now === null || before === null || before === undefined) return null;
  const points = Math.round((now - before) * 100);
  if (points === 0) return <span className="text-muted">same as version {version}</span>;
  return (
    <span className={cn("font-semibold", points > 0 ? "text-success" : "text-danger")}>
      {points > 0 ? "▲" : "▼"} {Math.abs(points)} pts
      {version !== undefined && (
        <span className="font-normal text-muted"> on version {version}</span>
      )}
    </span>
  );
}

/** Of the runs started, how many answered each question and how many reached the end. */
export function Funnel({ steps }: { steps: NonNullable<LessonInsights["funnel"]> }) {
  const started = steps[0]?.runs ?? 0;
  if (!started) return null;
  let biggest = { drop: 0, after: 0 };
  steps.forEach((step, i) => {
    const drop = i > 0 ? steps[i - 1].runs - step.runs : 0;
    if (drop > biggest.drop) biggest = { drop, after: i };
  });
  const label = (question: number | null, i: number) =>
    question === null
      ? "Reached the end"
      : i === 0
        ? `Started (answered question ${question})`
        : `Answered question ${question}`;

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-3">
        {steps.map((step, i) => (
          <li key={step.question ?? "end"} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-ink">{label(step.question, i)}</span>
              <span className="shrink-0 text-xs text-muted tabular-nums">
                <span className="font-semibold text-ink">{step.runs}</span> ·{" "}
                {percent(step.runs / started)}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-surface">
              <div
                className="h-full rounded-full bg-ink transition-[width] duration-500"
                style={{ width: `${(step.runs / started) * 100}%`, opacity: 1 - i * 0.15 }}
              />
            </div>
          </li>
        ))}
      </ol>
      {biggest.drop > 0 && (
        <p className="text-xs text-muted">
          Most who stop leave{" "}
          {steps[biggest.after].question === null
            ? `after the last question`
            : `between question ${steps[biggest.after - 1].question} and question ${steps[biggest.after].question}`}
          .
        </p>
      )}
    </div>
  );
}

/** How many learners got 0, 1, 2… questions right on their first run. */
export function ScoreSpread({ scores }: { scores: NonNullable<LessonInsights["scores"]> }) {
  const total = scores.reduce((sum, s) => sum + s.learners, 0);
  const most = Math.max(1, ...scores.map((s) => s.learners));
  const top = scores.length - 1;
  return (
    <div className="flex h-44 items-end gap-3">
      {scores.map((s) => (
        <div
          key={s.correct}
          className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1.5"
          title={`${s.learners} learners got ${s.correct} of ${top} right`}
        >
          <span className="text-sm font-semibold text-ink tabular-nums">
            {total ? percent(s.learners / total) : "0%"}
          </span>
          <div
            className={cn(
              "w-full max-w-16 rounded-t-md transition-[height] duration-500",
              BAND_FILL[band(top ? s.correct / top : 1)],
            )}
            style={{ height: `${Math.max(4, (s.learners / most) * 100)}px` }}
          />
          <span className="text-xs text-muted">
            {s.correct} of {top}
          </span>
        </div>
      ))}
    </div>
  );
}

function verdict(question: InsightsQuestion): { text: string; tone: Band } {
  const right = question.right_first_time;
  const lure = Math.max(0, ...question.options.filter((o) => !o.correct).map((o) => o.chosen));
  if (lure > right) return { text: "Most picked a wrong answer", tone: "poor" };
  if (right < 0.5) return { text: "Under half right first time", tone: "poor" };
  if (right < 0.75) return { text: "Could be clearer", tone: "fair" };
  return { text: "Working well", tone: "good" };
}

const CHIP: Record<Band, string> = {
  good: "bg-success-soft text-success",
  fair: "bg-amber-50 text-amber-800",
  poor: "bg-danger text-white",
};

/**
 * One question (SCRUM-84 AC2): how often each option was chosen first time, with the right
 * one ticked and the most popular wrong one in red, then right first time, whether retakes
 * fix it, and how newcomers and Singaporeans differ.
 */
export function QuestionCard({
  question,
  previousVersion,
  showGroups,
  onView,
}: {
  question: InsightsQuestion;
  previousVersion: number | undefined;
  showGroups: boolean;
  onView: () => void;
}) {
  const { text, tone } = verdict(question);
  const wrong = question.options.filter((o) => !o.correct);
  const lure = wrong.reduce<(typeof wrong)[number] | null>(
    (top, o) => (o.chosen > (top?.chosen ?? 0) ? o : top),
    null,
  );
  const options = [
    ...question.options.filter((o) => o.correct),
    ...wrong.sort((a, b) => b.chosen - a.chosen),
  ];

  return (
    <article
      className={cn(
        "flex flex-col gap-4 rounded-lg border border-line bg-white p-4 sm:p-5",
        tone === "poor" && "shadow-[inset_3px_0_0_0_var(--color-danger)]",
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="flex flex-wrap items-center gap-2 text-2xs font-semibold tracking-wider text-muted uppercase">
            Question {question.number} · card {question.card_number}
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-2xs font-semibold tracking-normal normal-case",
                CHIP[tone],
              )}
            >
              {tone === "good" && <Check className="mr-0.5 inline size-3" aria-hidden />}
              {text}
            </span>
          </p>
          <LessonText
            text={question.text}
            className="text-[15px] leading-snug font-medium text-ink"
            renderBlank={() => (
              <span
                className="mx-0.5 inline-block w-10 border-b-2 border-ink/60"
                aria-label="blank"
              />
            )}
          />
        </div>
        <button
          type="button"
          onClick={onView}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-sm text-xs font-semibold text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          <Eye className="size-3.5" aria-hidden />
          View card
        </button>
      </header>

      <ul
        className="flex flex-col gap-2.5"
        aria-label="How often each option was chosen first time"
      >
        {options.map((option) => (
          <li
            key={option.id}
            className="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-x-3 gap-y-1"
          >
            <span className="flex min-w-0 items-center gap-2 text-sm text-ink">
              {option.correct ? (
                <Check className="size-4 shrink-0 text-success" aria-label="Right answer" />
              ) : (
                <span className="size-4 shrink-0" aria-hidden />
              )}
              <span className="min-w-0 break-words">{option.text}</span>
            </span>
            <span className="row-span-2 text-right text-sm font-semibold tabular-nums">
              {percent(option.chosen)}
            </span>
            <div className="ml-6 h-2 overflow-hidden rounded-full bg-surface">
              <div
                className={cn(
                  "h-full rounded-full transition-[width] duration-500",
                  option.correct
                    ? "bg-success"
                    : option === lure && tone === "poor"
                      ? "bg-danger"
                      : "bg-subtle/60",
                )}
                style={{ width: `${option.chosen * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>

      <dl className="grid gap-4 border-t border-line pt-4 text-xs text-muted sm:grid-cols-3">
        <div className="flex flex-col gap-1">
          <dt>Right first time</dt>
          <dd className="flex flex-wrap items-baseline gap-x-2 text-base font-semibold text-ink tabular-nums">
            {percent(question.right_first_time)}
            <span className="text-xs">
              <Change
                now={question.right_first_time}
                before={question.previous_right_first_time}
                version={previousVersion}
              />
            </span>
          </dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt>Wrong, then right on a retake</dt>
          <dd className="text-base font-semibold text-ink tabular-nums">
            {question.fixed_on_retake === null ? (
              <span className="text-xs font-normal text-muted">Under 5 retook it</span>
            ) : (
              percent(question.fixed_on_retake)
            )}
          </dd>
        </div>
        {showGroups && (
          <div className="flex flex-col gap-1.5">
            <dt>Right first time by learner</dt>
            {(
              [
                ["Newcomers", question.newcomers, "bg-[#2a78d6]"],
                ["Singaporeans", question.singaporeans, "bg-[#eb6834]"],
              ] as const
            ).map(([label, share, fill]) => (
              <dd
                key={label}
                className="grid grid-cols-[5.5rem_minmax(0,1fr)_2.5rem] items-center gap-2"
              >
                <span>{label}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-surface">
                  {share !== null && (
                    <span
                      className={cn("block h-full rounded-full", fill)}
                      style={{ width: `${share * 100}%` }}
                    />
                  )}
                </span>
                <span className="text-right font-semibold text-ink tabular-nums">
                  {share === null ? (
                    <span className="font-normal text-subtle">–</span>
                  ) : (
                    percent(share)
                  )}
                </span>
              </dd>
            ))}
          </div>
        )}
      </dl>
    </article>
  );
}
