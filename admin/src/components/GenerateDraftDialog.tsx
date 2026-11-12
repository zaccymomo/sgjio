import { Alert, ApiError, Button, cn, Dialog, Spinner, TextAreaField } from "@sgjio/ui";
import { Sparkles } from "lucide-react";
import { useEffect, useId, useState, type ComponentProps, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import type { Topic } from "../lib/content";
import {
  CARD_CHOICES,
  generationApi,
  MAX_NOTES,
  type CardChoice,
  type GenerationQuota,
} from "../lib/generation";
import { LEVEL_DESCRIPTIONS, LEVELS, levelLabel } from "../lib/levels";

const POLL_MS = 1500;

/** The Content page's "Generate draft" button: outlined in brand red, with sparkles. */
export function GenerateDraftButton({ className, ...props }: ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-11 items-center justify-center gap-2 rounded-sm border border-brand bg-brand-soft px-4 text-sm font-semibold text-rose-700 transition-colors hover:bg-rose-100",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    >
      <Sparkles className="size-4" aria-hidden />
      Generate draft
    </button>
  );
}

type Phase =
  { step: "form" } | { step: "writing"; jobId: string } | { step: "failed"; message: string };

/**
 * Ask the AI for a Draft lesson (docs/ai-lessons-plan.md, section 6): topic, level, what to
 * teach and length. Then waits, asking every 1.5 seconds, and opens the new draft in the
 * editor; or says why it failed, with Try again. The form keeps what was typed.
 */
export function GenerateDraftDialog({
  open,
  topics,
  onClose,
}: {
  open: boolean;
  topics: Topic[];
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const formId = useId();
  const active = topics.filter((topic) => topic.archived_at === null);
  const [topicId, setTopicId] = useState("");
  const [level, setLevel] = useState(1);
  const [notes, setNotes] = useState("");
  const [cards, setCards] = useState<CardChoice>(6);
  const [notesError, setNotesError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [quota, setQuota] = useState<GenerationQuota | null>(null);
  const [phase, setPhase] = useState<Phase>({ step: "form" });

  // How many are left, fresh each time it opens.
  useEffect(() => {
    if (!open) return;
    generationApi
      .quota()
      .then(setQuota)
      .catch(() => setQuota(null));
  }, [open]);

  // Opens fresh next time, apart from the fields.
  function close() {
    setPhase({ step: "form" });
    setFormError(undefined);
    onClose();
  }

  const chosenTopic = active.some((topic) => topic.id === topicId) ? topicId : active[0]?.id;

  // While writing: ask how it is going until it is done or failed.
  const jobId = phase.step === "writing" ? phase.jobId : null;
  useEffect(() => {
    if (!open || !jobId) return;
    let stopped = false;
    let timer: number | undefined;
    async function poll() {
      try {
        const job = await generationApi.get(jobId!);
        if (stopped) return;
        setQuota((current) => current && { ...current, left_today: job.left_today });
        if (job.status === "done" && job.lesson_id) {
          navigate(`/lessons/${job.lesson_id}`);
          return;
        }
        if (job.status === "failed") {
          setPhase({
            step: "failed",
            message: job.failure?.message ?? "We couldn't write this draft. Please try again.",
          });
          return;
        }
      } catch {
        // A blip: keep asking. The request times out on the server after 90 seconds.
      }
      if (!stopped) timer = window.setTimeout(() => void poll(), POLL_MS);
    }
    timer = window.setTimeout(() => void poll(), POLL_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [open, jobId, navigate]);

  const trimmed = notes.trim();
  const left = quota?.left_today;
  const noneLeft = left === 0;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(undefined);
    if (trimmed === "") return setNotesError("Write what the lesson should teach.");
    if (trimmed.length > MAX_NOTES) {
      return setNotesError(`Use ${MAX_NOTES} characters or fewer. This has ${trimmed.length}.`);
    }
    if (!chosenTopic) return setFormError("Create a topic first.");
    setSubmitting(true);
    try {
      const job = await generationApi.request({
        topic_id: chosenTopic,
        level,
        notes: trimmed,
        cards,
      });
      setQuota((current) => current && { ...current, left_today: job.left_today });
      setPhase({ step: "writing", jobId: job.id });
    } catch (error) {
      if (error instanceof ApiError && error.code === "daily_limit_reached") {
        setQuota((current) => current && { ...current, left_today: 0 });
      }
      setFormError(
        error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const writing = phase.step === "writing";
  return (
    <Dialog
      open={open}
      title="Generate a draft lesson"
      description="It arrives as a Draft. Learners see nothing until you review and publish it."
      onClose={close}
      dismissible={!submitting}
      footer={
        writing ? undefined : phase.step === "failed" ? (
          <>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button onClick={() => setPhase({ step: "form" })} disabled={noneLeft}>
              Try again
            </Button>
          </>
        ) : (
          <>
            {quota && (
              <p className="self-center text-xs text-muted sm:mr-auto">
                {quota.left_today} of {quota.daily_limit} drafts remaining today
              </p>
            )}
            <Button variant="secondary" onClick={close} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form={formId} loading={submitting} disabled={noneLeft}>
              <Sparkles className="size-4" aria-hidden />
              Generate draft
            </Button>
          </>
        )
      }
    >
      {writing && (
        <div className="flex flex-col items-center gap-3 py-8 text-center" role="status">
          <Spinner className="size-6 text-brand" />
          <p className="text-sm font-semibold text-ink">Preparing your draft…</p>
          <p className="text-xs text-muted">Usually under a minute</p>
        </div>
      )}

      {phase.step === "failed" && <Alert tone="error">{phase.message}</Alert>}

      {phase.step === "form" && (
        <form id={formId} onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          {formError && <Alert tone="error">{formError}</Alert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-xs font-semibold text-ink">
              Topic
              <select
                className="h-11 w-full rounded-sm border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink/10"
                value={chosenTopic ?? ""}
                onChange={(event) => setTopicId(event.target.value)}
              >
                {active.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-semibold text-ink">
              <span>
                Level <span className="font-normal text-muted">(fixed once published)</span>
              </span>
              <select
                className="h-11 w-full rounded-sm border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink/10"
                value={level}
                onChange={(event) => setLevel(Number(event.target.value))}
              >
                {LEVELS.map((value) => (
                  <option key={value} value={value} title={LEVEL_DESCRIPTIONS[value]}>
                    {levelLabel(value)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <TextAreaField
            label="What should it teach?"
            data-autofocus
            rows={5}
            placeholder="For example: saying no to a manager is usually indirect, like “can try, but…”."
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
              setNotesError(undefined);
            }}
            error={notesError}
            hint={`The draft is based only on these notes and the topic's existing lessons. ${trimmed.length} / ${MAX_NOTES}`}
          />
          <div className="flex flex-col gap-1.5">
            <span id={`${formId}-length`} className="text-xs font-semibold text-ink">
              Length
            </span>
            <div
              role="radiogroup"
              aria-labelledby={`${formId}-length`}
              className="inline-flex self-start rounded-sm border border-line bg-surface p-0.5"
            >
              {CARD_CHOICES.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  role="radio"
                  aria-checked={cards === choice}
                  onClick={() => setCards(choice)}
                  className={cn(
                    "h-9 rounded-sm px-4 text-sm font-medium transition-colors",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                    cards === choice ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
                  )}
                >
                  {choice} cards
                </button>
              ))}
            </div>
          </div>
        </form>
      )}
    </Dialog>
  );
}
