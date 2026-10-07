import { cn } from "@sgjio/ui";
import {
  checkLocally,
  LessonDeck,
  toLearnerCards,
  type Assets,
  type DeckLesson,
  type LessonDoc,
} from "@sgjio/ui/lesson";
import { Laptop, Smartphone, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Device = "phone" | "laptop";
const DEVICE_KEY = "sgjio-admin-preview-device";

function readDevice(): Device {
  try {
    return localStorage.getItem(DEVICE_KEY) === "laptop" ? "laptop" : "phone";
  } catch {
    return "phone";
  }
}

/**
 * A lesson exactly as learners will see it (SCRUM-65), over the whole page.
 *
 * It plays the shared LessonDeck, the same one learners get, from the document given, so it
 * shows unsaved edits too. Answers are checked in the browser: nothing is recorded against
 * any account or progress figure (AC2). Options are shuffled afresh each time it opens, as
 * they are for learners. "Phone" shows it at phone size in a frame; "Laptop" fills the
 * window. Closing (or Esc) returns to wherever it was opened from (AC3).
 */
export function LessonPreview({
  lesson,
  doc,
  assets,
  onClose,
}: {
  lesson: DeckLesson;
  doc: LessonDoc;
  assets: Assets;
  onClose: () => void;
}) {
  const [device, setDevice] = useState<Device>(readDevice);
  const [seed] = useState(() => Math.floor(Math.random() * 2 ** 31) + 1);
  const cards = useMemo(() => toLearnerCards(doc, seed), [doc, seed]);
  const check = useMemo(() => checkLocally(doc), [doc]);
  const questionCount = doc.cards.filter((card) => card.question).length;

  // The page behind stays put while the preview is open.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  function choose(next: Device) {
    setDevice(next);
    try {
      localStorage.setItem(DEVICE_KEY, next);
    } catch {
      // Not remembered; nothing else depends on it.
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Preview of ${lesson.title || "this lesson"}`}
      className="fixed inset-0 z-50 flex flex-col bg-[#e9ebf0]"
    >
      <div className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-white px-4">
        <span className="rounded-sm bg-brand px-2 py-0.5 text-2xs font-bold tracking-wide text-white uppercase">
          Preview
        </span>
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
          {lesson.title || "Untitled lesson"}
          <span className="ml-2 font-normal text-muted">Answers aren&rsquo;t recorded</span>
        </p>
        <div role="group" aria-label="Device" className="flex rounded-md bg-surface p-0.5">
          {(
            [
              { value: "phone", label: "Phone", icon: Smartphone },
              { value: "laptop", label: "Laptop", icon: Laptop },
            ] as const
          ).map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              aria-pressed={device === value}
              onClick={() => choose(value)}
              className={cn(
                "flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-xs font-semibold transition-colors",
                device === value ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold text-muted hover:bg-surface hover:text-ink"
        >
          <X className="size-4" aria-hidden />
          Close
        </button>
      </div>

      {questionCount === 0 && (
        <p className="shrink-0 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900">
          This lesson has no questions yet, so it can&rsquo;t be published. Add one to a card.
        </p>
      )}

      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4 md:p-6">
        {device === "phone" ? (
          <div className="h-[min(844px,100%)] w-[min(390px,100%)] overflow-hidden rounded-[48px] border-[10px] border-ink bg-white shadow-2xl">
            <LessonDeck
              lesson={lesson}
              cards={cards}
              assets={assets}
              check={check}
              onExit={onClose}
            />
          </div>
        ) : (
          <div className="h-full w-full overflow-hidden rounded-xl shadow-xl">
            <LessonDeck
              lesson={lesson}
              cards={cards}
              assets={assets}
              check={check}
              onExit={onClose}
            />
          </div>
        )}
      </div>
    </div>
  );
}
