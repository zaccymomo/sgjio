import { Alert, Button, Dialog, ErrorState, Spinner, cn } from "@sgjio/ui";
import { ChevronDown, ChevronLeft } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { MadeWithAi } from "../components/MadeWithAi";
import {
  DIFFICULTY_LABELS,
  LENGTH_LABELS,
  dailyLimitMessage,
  errorMessage,
  isDailyLimit,
  plural,
  startGeneration,
  useGenerateOptions,
  type Difficulty,
  type Focus,
  type GenerateChoices,
  type GenerateOptions,
  type Length,
} from "../lib/generated";

const MAX_ASK = 200;

const focusRing =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

/**
 * "Generate a lesson" (docs/ai-lessons-plan.md, step 2): topic, focus, an optional ask, how
 * hard and how long. "Practise N mistakes" opens it with ?focus=mistakes; "Change options"
 * passes the earlier choices in the location state.
 */
export function GeneratePage() {
  const { state, reload } = useGenerateOptions();

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/practice"
        className={cn(
          "inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink",
          focusRing,
        )}
      >
        <ChevronLeft className="size-4" aria-hidden />
        Practice
      </Link>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[22px] font-bold text-ink">Generate a lesson</h1>
          <MadeWithAi />
        </div>
        <p className="mt-1 text-sm text-muted">
          A short practice lesson based on what you have learnt so far. It does not affect your
          progress.
        </p>
      </div>

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading your options" />
        </div>
      )}
      {state.status === "error" && (
        <ErrorState message={state.message} onRetry={() => void reload()} />
      )}
      {state.status === "ready" && <GenerateForm options={state.options} />}
    </div>
  );
}

function GenerateForm({ options }: { options: GenerateOptions }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const earlier = (location.state as { choices?: GenerateChoices } | null)?.choices;

  // Earlier choices ("Change options"), else ?topic= from a topic page, else Pick for me.
  const wanted = earlier?.topic_id ?? params.get("topic");
  const [topicId, setTopicId] = useState(
    wanted && options.topics.some((t) => t.id === wanted) ? wanted : "",
  );
  const [focus, setFocus] = useState<Focus>(
    earlier?.focus ?? (params.get("focus") === "mistakes" ? "mistakes" : "new"),
  );
  const [ask, setAsk] = useState(earlier?.ask ?? "");
  const [difficulty, setDifficulty] = useState<Difficulty>(earlier?.difficulty ?? "right");
  const [length, setLength] = useState<Length>(earlier?.length ?? "usual");
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeSeen, setNoticeSeen] = useState(options.has_generated);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limitReached, setLimitReached] = useState(options.left_today <= 0);
  const [leftToday, setLeftToday] = useState(options.left_today);
  const topicHintId = useId();

  const topic = options.topics.find((t) => t.id === topicId) ?? null;
  const pickedForMistakes = options.topics.find((t) => t.id === options.pick_for_me.mistakes);
  // Mistakes in the chosen topic; for Pick for me, any at all (it picks the topic with most).
  const mistakes = topic ? topic.mistakes : options.mistakes_total;
  const mistakesTopic = topic?.name ?? pickedForMistakes?.name;
  const mistakesShown = topic ? topic.mistakes : (pickedForMistakes?.mistakes ?? 0);
  // My mistakes can't be chosen where there are none, even if it was asked for.
  const chosenFocus: Focus = focus === "mistakes" && mistakes === 0 ? "new" : focus;

  async function generate() {
    setSending(true);
    setError(null);
    try {
      const created = await startGeneration({
        topic_id: topicId || null,
        focus: chosenFocus,
        ask: ask.trim() || null,
        difficulty,
        length,
      });
      navigate(`/practice/generated/${created.id}`);
    } catch (failure) {
      setSending(false);
      if (isDailyLimit(failure)) {
        setLimitReached(true);
        setLeftToday(0);
        return;
      }
      setError(errorMessage(failure, "We couldn't start your lesson. Check your connection."));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (limitReached || sending) return;
    if (!noticeSeen) {
      setNoticeOpen(true);
      return;
    }
    void generate();
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="generate-topic" className="text-xs font-semibold text-ink">
          Topic
        </label>
        <div className="relative">
          <select
            id="generate-topic"
            value={topicId}
            onChange={(event) => setTopicId(event.target.value)}
            aria-describedby={topicHintId}
            className="h-11 w-full appearance-none rounded-sm border border-line bg-white pr-10 pl-3 text-sm text-ink transition-colors outline-none focus:border-ink focus:ring-2 focus:ring-ink/10"
          >
            <option value="">Pick for me</option>
            {options.topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-subtle"
            aria-hidden
          />
        </div>
        <p id={topicHintId} className="text-xs text-muted">
          {topic
            ? `Builds on the lessons in ${topic.name}.`
            : "We will choose the topic you have practised least, or the one where you answered the most questions incorrectly."}
        </p>
      </div>

      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 text-xs font-semibold text-ink">Focus on</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          <FocusCard
            value="new"
            checked={chosenFocus === "new"}
            onChange={setFocus}
            title="Something new"
            text={`Covers something not yet taught in ${topic?.name ?? "the topic you have practised least"}`}
          />
          <FocusCard
            value="mistakes"
            checked={chosenFocus === "mistakes"}
            onChange={setFocus}
            disabled={mistakes === 0}
            title="My mistakes"
            text={
              mistakes === 0
                ? `No incorrect answers in ${topic?.name ?? "any topic"} yet`
                : `Revisits the ${plural(mistakesShown, "question", "questions")} you answered incorrectly in ${mistakesTopic}`
            }
          />
        </div>
      </fieldset>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="generate-ask" className="text-xs font-semibold text-ink">
          Anything in particular? <span className="font-normal text-muted">(Optional)</span>
        </label>
        <textarea
          id="generate-ask"
          rows={3}
          value={ask}
          maxLength={MAX_ASK}
          onChange={(event) => setAsk(event.target.value)}
          aria-describedby="generate-ask-count"
          placeholder="For example, how to reply when colleagues ask “can or not?”"
          className="w-full resize-y rounded-sm border border-line bg-white px-3 py-2.5 text-sm text-ink transition-colors outline-none placeholder:text-subtle focus:border-ink focus:ring-2 focus:ring-ink/10"
        />
        <p id="generate-ask-count" className="text-right text-xs text-muted">
          {ask.length} / {MAX_ASK}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Segmented
          label="How hard"
          value={difficulty}
          onChange={setDifficulty}
          choices={DIFFICULTY_LABELS}
        />
        <Segmented label="Length" value={length} onChange={setLength} choices={LENGTH_LABELS} />
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <div className="flex flex-col gap-2">
        {limitReached && <Alert>{dailyLimitMessage(options.daily_limit)}</Alert>}
        <Button
          type="submit"
          // Greyed out once today's lessons are used up.
          variant={limitReached ? "secondary" : "accent"}
          fullWidth
          loading={sending}
          disabled={limitReached}
          className="h-12 text-base"
        >
          Generate lesson
        </Button>
        <p className="text-center text-caption text-muted">
          {leftToday} remaining today. AI-generated lessons may contain errors; use the flag on any
          card to report one.
        </p>
      </div>

      <Dialog
        open={noticeOpen}
        title="Before your first AI lesson"
        onClose={() => setNoticeOpen(false)}
        footer={
          <Button
            variant="accent"
            data-autofocus
            onClick={() => {
              setNoticeOpen(false);
              setNoticeSeen(true);
              void generate();
            }}
          >
            Got it
          </Button>
        }
      >
        <ul className="flex list-disc flex-col gap-2 pl-5 text-sm text-ink">
          <li>
            Each lesson is written by AI and has not been reviewed by our team. Please flag anything
            that looks incorrect.
          </li>
          <li>It is additional practice and does not count towards your progress or portfolio.</li>
          <li>
            It is based on your progress and anything you type. Your name and email address are
            never shared.
          </li>
        </ul>
      </Dialog>
    </form>
  );
}

function FocusCard({
  value,
  checked,
  disabled,
  onChange,
  title,
  text,
}: {
  value: Focus;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: Focus) => void;
  title: string;
  text: string;
}) {
  return (
    <label
      className={cn(
        "flex items-start gap-2.5 rounded-md border p-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand",
        disabled
          ? "cursor-not-allowed border-dashed border-line bg-surface"
          : checked
            ? "cursor-pointer border-brand bg-brand-soft/50"
            : "cursor-pointer border-line bg-white hover:bg-surface",
      )}
    >
      <input
        type="radio"
        name="focus"
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="mt-0.5 size-4 accent-brand"
      />
      <span className="flex flex-col">
        <span className={cn("text-sm font-semibold", disabled ? "text-subtle" : "text-ink")}>
          {title}
        </span>
        <span className="text-caption text-muted">{text}</span>
      </span>
    </label>
  );
}

function Segmented<T extends string>({
  label,
  value,
  onChange,
  choices,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  choices: Record<T, ReactNode>;
}) {
  const labelId = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <span id={labelId} className="text-xs font-semibold text-ink">
        {label}
      </span>
      <div
        role="group"
        aria-labelledby={labelId}
        className="flex gap-1 rounded-md border border-line bg-surface p-1"
      >
        {(Object.keys(choices) as T[]).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={value === key}
            onClick={() => onChange(key)}
            className={cn(
              "min-h-9 flex-1 rounded-sm px-2 text-xs font-semibold transition-colors",
              focusRing,
              value === key
                ? "border border-brand bg-white text-brand shadow-sm"
                : "text-muted hover:text-ink",
            )}
          >
            {choices[key]}
          </button>
        ))}
      </div>
    </div>
  );
}
