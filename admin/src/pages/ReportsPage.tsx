import { Alert, ApiError, Button, ErrorState, Spinner, cn } from "@sgjio/ui";
import { ChevronLeft, ExternalLink, Flag, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { formatDateTime, formatRelative, plural } from "../lib/format";
import { REASON_LABELS, reportApi, type Report, type ReportStatus } from "../lib/reports";

type Which = "open" | "closed";

const VIEWS: Array<{ value: Which; label: string }> = [
  { value: "open", label: "Open" },
  { value: "closed", label: "Fixed or dismissed" },
];

type Load =
  | { status: "loading" }
  | { status: "ready"; reports: Report[] }
  | { status: "error"; message: string };

const STATUS_LABELS: Record<ReportStatus, string> = {
  open: "Open",
  fixed: "Fixed",
  dismissed: "Dismissed",
};

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/**
 * Reported problems (SCRUM-83): what learners flagged on lesson cards (SCRUM-82).
 *
 * Open reports come newest first, with the lesson, the card, the reason, the note and the
 * date, and never who sent them (AC1). Each leads straight to its card in the lesson editor
 * (AC2). Marking one Fixed or Dismissed takes it off the open list; it is kept under "Fixed
 * or dismissed", where it can be reopened (AC3). `?lesson=<id>`, from a lesson's count on
 * the content page (AC4), shows only that lesson's reports.
 */
export function ReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const which: Which = searchParams.get("view") === "closed" ? "closed" : "open";
  const lessonId = searchParams.get("lesson");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; message: string } | null>(null);

  // Success messages clear themselves, as on the content page; errors stay until replaced.
  useEffect(() => {
    if (notice?.tone !== "success") return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const controller = new AbortController();
    reportApi
      .list(which, controller.signal)
      .then((reports) => setLoad({ status: "ready", reports }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoad({
          status: "error",
          message: messageOf(error, "We couldn't load the reports. Please try again."),
        });
      });
    return () => controller.abort();
  }, [which, attempt]);

  const changeParams = useCallback(
    (change: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(change)) {
        if (value === null) next.delete(key);
        else next.set(key, value);
      }
      // Another list: show the spinner until it has loaded.
      if ("view" in change) setLoad({ status: "loading" });
      setSearchParams(next, { replace: true });
      setNotice(null);
    },
    [searchParams, setSearchParams],
  );

  async function setStatus(report: Report, status: ReportStatus) {
    setBusyId(report.id);
    setNotice(null);
    try {
      await reportApi.setStatus(report.id, status);
      // It now belongs to the other list.
      setLoad((current) =>
        current.status === "ready"
          ? { ...current, reports: current.reports.filter((r) => r.id !== report.id) }
          : current,
      );
      setNotice({
        tone: "success",
        message:
          status === "open"
            ? "Report reopened."
            : `Report marked ${STATUS_LABELS[status].toLowerCase()}. It's kept under “Fixed or dismissed”.`,
      });
    } catch (error) {
      setNotice({
        tone: "error",
        message: messageOf(error, "We couldn't update that report. Please try again."),
      });
    } finally {
      setBusyId(null);
    }
  }

  const reports =
    load.status === "ready"
      ? load.reports.filter((report) => !lessonId || report.lesson_id === lessonId)
      : [];
  const lessonTitle =
    lessonId && load.status === "ready"
      ? load.reports.find((report) => report.lesson_id === lessonId)?.lesson_title
      : undefined;

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        All content
      </Link>

      <div>
        <h1 className="text-xl font-bold text-ink">Reported problems</h1>
        <p className="mt-1 text-sm text-muted">
          Cards learners flagged as wrong, outdated, insensitive or broken. Who sent a report is
          never shown.
        </p>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div
          role="group"
          aria-label="Which reports"
          className="flex rounded-md border border-line bg-surface p-0.5 sm:inline-flex"
        >
          {VIEWS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={which === value}
              onClick={() =>
                value !== which && changeParams({ view: value === "open" ? null : value })
              }
              className={cn(
                "h-8 flex-1 rounded-sm px-3 text-xs font-semibold transition-colors sm:flex-none",
                "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand",
                which === value ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {lessonId && (
          <div className="flex items-center justify-between gap-2 sm:justify-end">
            <p className="text-caption text-muted">
              Only {lessonTitle ? `“${lessonTitle}”` : "one lesson"}
            </p>
            <Button variant="ghost" size="sm" onClick={() => changeParams({ lesson: null })}>
              <X className="size-3.5" aria-hidden />
              Show all lessons
            </Button>
          </div>
        )}
      </div>

      {notice && <Alert tone={notice.tone}>{notice.message}</Alert>}

      {load.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading reports" />
        </div>
      )}
      {load.status === "error" && (
        <ErrorState
          message={load.message}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      )}
      {load.status === "ready" &&
        (reports.length === 0 ? (
          <section className="rounded-lg border border-line bg-white p-6 text-center">
            <p className="text-sm font-semibold text-ink">
              {which === "open" ? "No open reports" : "Nothing fixed or dismissed yet"}
            </p>
            <p className="mt-1 text-sm text-muted">
              {which === "open"
                ? "When learners report a problem on a card, it appears here."
                : "Reports you mark fixed or dismissed are kept here for reference."}
            </p>
          </section>
        ) : (
          <>
            <p className="sr-only" role="status">
              {plural(reports.length, which === "open" ? "open report" : "report")}
            </p>
            <ul className="flex flex-col gap-2.5">
              {reports.map((report) => (
                <li key={report.id}>
                  <ReportCard
                    report={report}
                    busy={busyId === report.id}
                    onSetStatus={(status) => void setStatus(report, status)}
                  />
                </li>
              ))}
            </ul>
          </>
        ))}
    </div>
  );
}

function ReportCard({
  report,
  busy,
  onSetStatus,
}: {
  report: Report;
  busy: boolean;
  onSetStatus: (status: ReportStatus) => void;
}) {
  const card = report.card_number ? `Card ${report.card_number}` : "A card";
  const editorLink = report.card_in_draft
    ? `/lessons/${report.lesson_id}?card=${encodeURIComponent(report.card_id)}`
    : `/lessons/${report.lesson_id}`;

  return (
    <article className="flex flex-col gap-3 rounded-lg border border-line bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold break-words text-ink">
            {report.lesson_title || "Untitled lesson"}
          </h2>
          <p className="text-caption text-muted">
            {report.topic_name && <>{report.topic_name} · </>}
            {card} of version {report.version}
          </p>
        </div>
        <p className="text-caption text-muted">
          <time dateTime={report.created_at} title={formatDateTime(report.created_at)}>
            {formatDateTime(report.created_at)}
          </time>
        </p>
      </div>

      {report.card_excerpt && (
        <blockquote className="rounded-md border-l-4 border-line bg-surface px-3 py-2 text-sm text-ink">
          {report.card_excerpt}
        </blockquote>
      )}

      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
        <dt className="text-caption font-semibold text-muted">Reason</dt>
        <dd className="inline-flex items-center gap-1.5 font-semibold text-ink">
          <Flag className="size-3.5 text-danger" aria-hidden />
          {REASON_LABELS[report.reason]}
        </dd>
        <dt className="text-caption font-semibold text-muted">Note</dt>
        <dd
          className={cn(
            "break-words whitespace-pre-line",
            report.note ? "text-ink" : "text-subtle",
          )}
        >
          {report.note || "No note"}
        </dd>
        {report.status !== "open" && report.resolved_at && (
          <>
            <dt className="text-caption font-semibold text-muted">Status</dt>
            <dd className="text-ink">
              {STATUS_LABELS[report.status]} {formatRelative(report.resolved_at)}
            </dd>
          </>
        )}
      </dl>

      <div className="flex flex-col gap-2 border-t border-line pt-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-0.5">
          <Link
            to={editorLink}
            className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-semibold text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {report.card_in_draft ? `Open ${card.toLowerCase()} in the editor` : "Open the lesson"}
            <ExternalLink className="size-3.5" aria-hidden />
          </Link>
          {!report.card_in_draft && (
            <p className="text-caption text-muted">
              This card has since been removed from the draft.
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {report.status === "open" ? (
            <>
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => onSetStatus("dismissed")}
              >
                Dismiss
              </Button>
              <Button size="sm" loading={busy} onClick={() => onSetStatus("fixed")}>
                Mark fixed
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              loading={busy}
              onClick={() => onSetStatus("open")}
            >
              Reopen
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}
