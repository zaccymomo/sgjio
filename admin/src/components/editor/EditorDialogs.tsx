import { Alert, Button, cn, Dialog } from "@sgjio/ui";
import type { Issue } from "@sgjio/ui/lesson";
import { AlertTriangle, ArrowRight, CircleX } from "lucide-react";
import type { ReactNode } from "react";

/** A yes-or-cancel question about an action, with what it will do. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      dismissible={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy} data-autofocus>
            Cancel
          </Button>
          <Button onClick={onConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm text-muted">
        {error && <Alert tone="error">{error}</Alert>}
        {children}
      </div>
    </Dialog>
  );
}

/**
 * What still stops a lesson being published (SCRUM-56, SCRUM-70), and what is worth a look,
 * each with a way to the card it is about.
 */
export function IssuesDialog({
  open,
  issues,
  cardNumber,
  onGoTo,
  onClose,
}: {
  open: boolean;
  issues: Issue[];
  /** The card's number (from 1), for an issue about a card. */
  cardNumber: (cardId: string) => number | null;
  onGoTo: (issue: Issue) => void;
  onClose: () => void;
}) {
  const blockers = issues.filter((issue) => issue.severity === "blocker");
  const warnings = issues.filter((issue) => issue.severity === "warning");
  const row = (issue: Issue, n: number) => {
    const number = issue.card_id ? cardNumber(issue.card_id) : null;
    const Icon = issue.severity === "blocker" ? CircleX : AlertTriangle;
    return (
      <li key={`${issue.code}-${issue.card_id}-${issue.field}-${n}`}>
        <button
          type="button"
          onClick={() => onGoTo(issue)}
          className="flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left hover:bg-surface"
        >
          <Icon
            className={cn(
              "mt-0.5 size-4 shrink-0",
              issue.severity === "blocker" ? "text-danger" : "text-amber-600",
            )}
            aria-hidden
          />
          <span className="flex-1 text-sm text-ink">
            {number !== null && <span className="font-semibold">Card {number}: </span>}
            {issue.message}
          </span>
          <ArrowRight className="mt-0.5 size-4 shrink-0 text-subtle" aria-hidden />
        </button>
      </li>
    );
  };
  return (
    <Dialog
      open={open}
      title={blockers.length ? "Not ready to publish yet" : "Worth a look before publishing"}
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose} data-autofocus>
          Back to editing
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        {blockers.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-bold tracking-wide text-muted uppercase">
              To fix before publishing
            </p>
            <ul>{blockers.map(row)}</ul>
          </div>
        )}
        {warnings.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-bold tracking-wide text-muted uppercase">
              Worth a look (these don&rsquo;t stop publishing)
            </p>
            <ul>{warnings.map(row)}</ul>
          </div>
        )}
      </div>
    </Dialog>
  );
}
