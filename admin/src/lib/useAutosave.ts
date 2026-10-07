import { ApiError } from "@sgjio/ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { draftOf, lessonApi, sameDraft, type Draft, type Lesson } from "./lessons";

/**
 * - idle: nothing to save
 * - pending: changed, saving shortly
 * - saving: a save is running
 * - error: the last save failed; the next change, or Save now, tries again
 * - conflict: changed elsewhere since it was loaded; saving stops until the latest is loaded
 * - signed-out: the session ended; saving stops until the administrator signs in again
 */
export type SaveStatus = "idle" | "pending" | "saving" | "error" | "conflict" | "signed-out";

const DELAY_MS = 1200;

/**
 * Saves the editor's draft by itself (SCRUM-19), a moment after the last change.
 *
 * Users never see a draft, only published versions, so saving as you go is safe. Saves run
 * one at a time: a change made while one is running is saved straight after it. A lesson
 * that has not been created yet is created by its first save (`onCreated`), so opening the
 * editor and leaving never leaves an empty lesson behind.
 *
 * `flush()` saves now and says whether everything is saved, for anything that must not run
 * on an older version: publishing, leaving the page. `adopt(lesson)` takes a version of the
 * lesson from elsewhere (after publishing, or loading the latest) as the saved one.
 */
export function useAutosave({
  lesson,
  draft,
  onSaved,
}: {
  lesson: Lesson | null;
  draft: Draft;
  /** Called with the server's lesson after each save; `created` for the first of a new one. */
  onSaved: (lesson: Lesson, created: boolean) => void;
}) {
  const [saved, setSaved] = useState<Draft>(() => draft);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const lessonRef = useRef(lesson);
  const draftRef = useRef(draft);
  const savedRef = useRef(saved);
  const running = useRef<Promise<boolean> | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const onSavedRef = useRef(onSaved);
  const stopped = status === "conflict" || status === "signed-out";
  const dirty = !sameDraft(draft, saved);

  useEffect(() => {
    draftRef.current = draft;
    onSavedRef.current = onSaved;
  });

  const save = useCallback(async (): Promise<boolean> => {
    window.clearTimeout(timer.current);
    if (running.current) await running.current;
    const sending = draftRef.current;
    if (sameDraft(sending, savedRef.current)) return true;

    setStatus("saving");
    const run = (async () => {
      const existing = lessonRef.current;
      try {
        const result = existing
          ? await lessonApi.save(existing, sending)
          : await lessonApi.create(sending);
        lessonRef.current = result;
        savedRef.current = sending;
        setSaved(sending);
        setMessage(null);
        onSavedRef.current(result, !existing);
        return true;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setStatus("signed-out");
        } else if (
          error instanceof ApiError &&
          (error.code === "lesson_out_of_date" || error.code === "lesson_not_found")
        ) {
          setStatus("conflict");
          setMessage(
            error.code === "lesson_not_found"
              ? "This lesson has been deleted since you opened it."
              : "This lesson was changed in another tab or by another administrator, so your " +
                  "latest changes weren't saved.",
          );
        } else {
          setStatus("error");
          setMessage(
            error instanceof ApiError
              ? error.code === "validation_error"
                ? (Object.values(error.fieldErrors)[0] ?? error.message)
                : error.message
              : "Something went wrong, so your latest changes weren't saved.",
          );
        }
        return false;
      }
    })();
    running.current = run;
    const ok = await run;
    running.current = null;
    if (ok) {
      // Anything typed while it ran is saved next, by the effect below.
      setStatus(sameDraft(draftRef.current, sending) ? "idle" : "pending");
    }
    return ok;
  }, []);

  // Save a moment after each change, unless saving has stopped. Runs again once a save
  // finishes (`saved` changes), to save anything typed while it ran.
  useEffect(() => {
    if (!dirty || stopped) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void save(), DELAY_MS);
    return () => window.clearTimeout(timer.current);
  }, [draft, saved, dirty, stopped, save]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const adopt = useCallback((next: Lesson) => {
    window.clearTimeout(timer.current);
    const nextDraft = draftOf(next);
    lessonRef.current = next;
    savedRef.current = nextDraft;
    setSaved(nextDraft);
    setStatus("idle");
    setMessage(null);
  }, []);

  /** Keep the latest server version (e.g. after publishing) without touching the draft. */
  const track = useCallback((next: Lesson) => {
    lessonRef.current = next;
  }, []);

  const shown: SaveStatus = status === "idle" && dirty ? "pending" : status;
  return {
    status: shown,
    message,
    dirty,
    flush: save,
    adopt,
    track,
  };
}
