import { apiFetch } from "@sgjio/ui";

export type ReportReason = "wrong" | "insensitive" | "typo" | "media" | "other";
export type ReportStatus = "open" | "fixed" | "dismissed";

/** The reasons learners pick from (SCRUM-82 AC1), as the portal names them. */
export const REASON_LABELS: Record<ReportReason, string> = {
  wrong: "Wrong or outdated",
  insensitive: "Insensitive",
  typo: "Typo",
  media: "Image or audio not working",
  other: "Other",
};

/** A reported problem as /api/admin/reports returns it: never who sent it (SCRUM-83 AC1). */
export type Report = {
  id: string;
  lesson_id: string;
  /** The lesson's title as it is now. */
  lesson_title: string;
  topic_name: string | null;
  /** The version the learner was shown, and the card's place in it (1-based). */
  version: number;
  card_id: string;
  card_number: number | null;
  card_excerpt: string;
  /** Whether the card is still in the draft, so the editor can open it. */
  card_in_draft: boolean;
  reason: ReportReason;
  note: string;
  status: ReportStatus;
  created_at: string;
  resolved_at: string | null;
};

const REPORTS = "/api/admin/reports";

export const reportApi = {
  list: (which: "open" | "closed", signal?: AbortSignal) =>
    apiFetch<Report[]>(`${REPORTS}?status=${which}`, { signal }),
  setStatus: (id: string, status: ReportStatus) =>
    apiFetch<Report>(`${REPORTS}/${id}/status`, { method: "PUT", body: { status } }),
};
