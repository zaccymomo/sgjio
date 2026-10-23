import { ApiError, cn, ErrorState, Spinner, useAuth } from "@sgjio/ui";
import { ChevronLeft, Eye, Pencil } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { Change, Funnel, QuestionCard, ScoreSpread } from "../components/insights/Figures";
import { TrendChart, type Metric } from "../components/insights/TrendChart";
import { LessonPreview } from "../components/LessonPreview";
import { formatDate } from "../lib/format";
import { insightsApi, percent, type LessonInsights, type Learners } from "../lib/insights";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "not-found" }
  | { status: "ready"; insights: LessonInsights; key: string };

const LEARNERS: { value: Learners; label: string }[] = [
  { value: "all", label: "Everyone" },
  { value: "newcomer", label: "Newcomers" },
  { value: "singaporean", label: "Singaporeans" },
];

const METRIC_TITLES: Record<Metric, string> = {
  learners: "Learners finishing it, each week",
  average_best: "Average best score so far",
  right_first_time: "Right first time so far",
  finish_rate: "Finish rate so far",
};

/**
 * How learners do on a lesson (SCRUM-84), at /lessons/:id/insights: one published version at
 * a time (AC4), for everyone or one kind of learner. Nothing is shown for a version fewer
 * than 5 learners have finished (AC3), and no learner is named (AC5). The version and the
 * learners are kept in the address, so the page can be bookmarked and Back works.
 */
export function LessonInsightsPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { refresh: recheckSession } = useAuth();
  const version = Number(params.get("version")) || undefined;
  const learners = (LEARNERS.find((l) => l.value === params.get("learners"))?.value ??
    "all") as Learners;
  const key = `${id}|${version ?? ""}|${learners}`;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    insightsApi
      .get(id, { version, learners }, controller.signal)
      .then((insights) => setLoad({ status: "ready", insights, key }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiError && error.status === 401) return void recheckSession();
        if (
          error instanceof ApiError &&
          ["lesson_not_found", "version_not_found", "validation_error"].includes(error.code)
        ) {
          return setLoad({ status: "not-found" });
        }
        setLoad({ status: "error", message: "We couldn't load these figures. Please try again." });
      });
    return () => controller.abort();
  }, [id, version, learners, key, attempt, recheckSession]);

  function choose(change: { version?: number; learners?: Learners }) {
    const next = new URLSearchParams(params);
    if (change.version !== undefined) next.set("version", String(change.version));
    if (change.learners !== undefined) {
      if (change.learners === "all") next.delete("learners");
      else next.set("learners", change.learners);
    }
    setParams(next, { replace: true });
  }

  if (load.status === "error") {
    return (
      <Frame>
        <ErrorState
          message={load.message}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      </Frame>
    );
  }
  if (load.status === "not-found") {
    return (
      <Frame>
        <p className="py-16 text-center text-base font-semibold text-ink">
          That lesson or version no longer exists
        </p>
      </Frame>
    );
  }
  if (load.status === "loading") {
    return (
      <Frame>
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading the figures" />
        </div>
      </Frame>
    );
  }
  return (
    <Insights
      insights={load.insights}
      // Old figures stay on screen, dimmed, while a new version or group loads.
      stale={load.key !== key}
      onChoose={choose}
    />
  );
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      {children}
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/"
      className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
    >
      <ChevronLeft className="size-4" aria-hidden />
      All content
    </Link>
  );
}

function Insights({
  insights,
  stale,
  onChoose,
}: {
  insights: LessonInsights;
  stale: boolean;
  onChoose: (change: { version?: number; learners?: Learners }) => void;
}) {
  const [metric, setMetric] = useState<Metric>("learners");
  const [preview, setPreview] = useState<{ start?: number } | null>(null);
  const { summary } = insights;
  const shown = insights.version;
  const previous = summary?.previous;

  const tiles: { metric: Metric; label: string; value: string; note: ReactNode }[] = summary
    ? [
        {
          metric: "learners",
          label: "Learners finished",
          value: String(summary.learners),
          note: `${percent(summary.share_of_learners)} of ${insights.learners === "all" ? "all learners" : "them"}`,
        },
        {
          metric: "average_best",
          label: "Average best score",
          value: percent(summary.average_best),
          note: previous ? (
            <Change
              now={summary.average_best}
              before={previous.average_best}
              version={previous.number}
            />
          ) : (
            "best run of each learner"
          ),
        },
        {
          metric: "right_first_time",
          label: "Right first time",
          value: summary.right_first_time === null ? "–" : percent(summary.right_first_time),
          note: previous ? (
            <Change
              now={summary.right_first_time}
              before={previous.right_first_time}
              version={previous.number}
            />
          ) : (
            "of first answers"
          ),
        },
        {
          metric: "finish_rate",
          label: "Finish rate",
          value: percent(summary.finish_rate),
          note: "of runs started",
        },
      ]
    : [];

  return (
    <div className="flex flex-col gap-5">
      <BackLink />

      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold tracking-wider text-brand uppercase">
            Insights
            {insights.topic_name && <span className="text-muted"> · {insights.topic_name}</span>}
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-balance text-ink sm:text-[28px]">
            {insights.title || "Untitled lesson"}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {insights.status === "withdrawn" ? "Withdrawn. " : ""}
            How learners do on each version. No one is named, and nothing shows for fewer than{" "}
            {insights.min_learners} learners.
          </p>
        </div>
        <div className="flex gap-2">
          {insights.doc && (
            <button
              type="button"
              onClick={() => setPreview({})}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3.5 text-sm font-semibold text-ink hover:bg-surface"
            >
              <Eye className="size-4" aria-hidden />
              Preview
            </button>
          )}
          <Link
            to={`/lessons/${insights.id}`}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-3.5 text-sm font-semibold text-white hover:bg-ink/90"
          >
            <Pencil className="size-4" aria-hidden />
            Edit lesson
          </Link>
        </div>
      </header>

      {insights.versions.length === 0 ? (
        <Notice title="Not published yet">
          Figures appear here once the lesson is published and learners have finished it.
        </Notice>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="insights-version">
              Version
            </label>
            <select
              id="insights-version"
              value={shown ?? ""}
              onChange={(event) => onChoose({ version: Number(event.target.value) })}
              className="h-10 max-w-full rounded-md border border-line bg-white pr-8 pl-3 text-sm text-ink"
            >
              {insights.versions.map((v, i) => (
                <option key={v.number} value={v.number}>
                  Version {v.number}
                  {i === 0 ? " (current)" : ""} · published {formatDate(v.published_at)}
                </option>
              ))}
            </select>
            <div
              role="group"
              aria-label="Learners"
              className="flex rounded-md bg-surface p-1 ring-1 ring-line"
            >
              {LEARNERS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={insights.learners === option.value}
                  onClick={() => onChoose({ learners: option.value })}
                  className={cn(
                    "rounded-sm px-3 py-1.5 text-xs font-semibold transition-colors",
                    insights.learners === option.value
                      ? "bg-white text-ink shadow-sm"
                      : "text-muted hover:text-ink",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className={cn("flex flex-col gap-5 transition-opacity", stale && "opacity-50")}>
            {summary ? (
              <div
                role="tablist"
                aria-label="Chart"
                className="grid grid-cols-2 gap-3 lg:grid-cols-4"
              >
                {tiles.map((tile) => (
                  <button
                    key={tile.metric}
                    type="button"
                    role="tab"
                    aria-selected={metric === tile.metric}
                    onClick={() => setMetric(tile.metric)}
                    className={cn(
                      "flex min-w-0 flex-col gap-0.5 rounded-lg border bg-white p-3.5 text-left transition-[border-color,box-shadow] sm:p-4",
                      metric === tile.metric
                        ? "border-ink shadow-[inset_0_0_0_1px_var(--color-ink)]"
                        : "border-line hover:border-subtle",
                    )}
                  >
                    <span className="text-xs font-medium text-muted">{tile.label}</span>
                    <span className="text-2xl font-bold tracking-tight text-ink tabular-nums sm:text-3xl">
                      {tile.value}
                    </span>
                    <span className="truncate text-xs text-muted">{tile.note}</span>
                  </button>
                ))}
              </div>
            ) : (
              <Notice
                title={`Figures appear once ${insights.min_learners} learners have finished this version`}
              >
                So no one&rsquo;s answers can be worked out from them.
                {insights.learners !== "all" && " Try “Everyone”, or another version."}
              </Notice>
            )}

            {insights.trend.series.length > 0 && shown !== null && (
              <Card
                title={summary ? METRIC_TITLES[metric] : "Learners finishing it, each week"}
                hint={
                  metric === "learners" || !summary
                    ? "Each learner counts once, in the week they first finished a version."
                    : "Each version's figure as it built up, so a rewrite shows as a step. A line starts once 5 learners have finished that version."
                }
              >
                <TrendChart
                  trend={insights.trend}
                  metric={summary ? metric : "learners"}
                  shownVersion={shown}
                />
              </Card>
            )}

            {insights.funnel && insights.scores && (
              <div className="grid gap-5 md:grid-cols-2">
                <Card title="Where learners stop" hint="Of the runs started on this version.">
                  <Funnel steps={insights.funnel} />
                </Card>
                <Card
                  title="First-try scores"
                  hint="How many questions each learner got right on their first run."
                >
                  <ScoreSpread scores={insights.scores} />
                </Card>
              </div>
            )}

            {insights.questions && insights.questions.length > 0 && (
              <section className="flex flex-col gap-3" aria-labelledby="questions-heading">
                <h2
                  id="questions-heading"
                  className="mt-2 text-lg font-bold tracking-tight text-ink"
                >
                  Questions
                </h2>
                {insights.questions.map((question) => (
                  <QuestionCard
                    key={question.id}
                    question={question}
                    previousVersion={previous?.number}
                    showGroups={insights.learners === "all"}
                    onView={() => setPreview({ start: question.card_number - 1 })}
                  />
                ))}
              </section>
            )}
          </div>
        </>
      )}

      {preview && insights.doc && (
        <LessonPreview
          lesson={{
            title: insights.title,
            topicName: insights.topic_name,
            readingSeconds: insights.reading_seconds,
          }}
          doc={insights.doc}
          assets={insights.assets}
          start={preview.start}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}

function Card({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-lg border border-line bg-white p-4 sm:p-5">
      <div>
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        <p className="mt-0.5 text-xs text-muted">{hint}</p>
      </div>
      {children}
    </section>
  );
}

function Notice({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-dashed border-line bg-white p-5">
      <span
        className="size-9 shrink-0 rounded-full bg-[repeating-linear-gradient(135deg,var(--color-surface)_0_4px,var(--color-line)_4px_6px)]"
        aria-hidden
      />
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="text-sm text-muted">{children}</p>
      </div>
    </div>
  );
}
