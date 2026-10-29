import { Spinner, cn } from "@sgjio/ui";
import { Check, Search } from "lucide-react";
import { Fragment, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { type SearchResult, useLessonSearch } from "../lib/search";

/**
 * Search every topic's published lessons from the landing page (SCRUM-85).
 *
 * Results drop down under the bar as the user types, each with its title, its topic and
 * whether it is completed (AC1), and the card text that matched. Nothing found reads "No
 * results available." (AC4), with the topic circles just below. Clearing the bar, or
 * selecting anywhere else, closes the list.
 *
 * The query is kept in the address (`/?q=chope`), and a lesson opened from here steps back
 * when it closes, so the user lands on the same results again (AC3).
 */
export function LessonSearch() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(() => params.get("q") ?? "");
  // Open on arrival when there is a query, which is how a closed lesson comes back here.
  const [open, setOpen] = useState(text.trim() !== "");
  const [active, setActive] = useState(-1);
  const { query, searchable, state, retry } = useLessonSearch(text);
  const box = useRef<HTMLDivElement>(null);
  const listId = useId();
  const optionId = (index: number) => `${listId}-${index}`;

  // Mirror the query into the address without adding a history entry per keystroke.
  useEffect(() => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (query) next.set("q", query);
        else next.delete("q");
        return next;
      },
      { replace: true },
    );
  }, [query, setParams]);

  // Selecting anywhere outside the bar and its list closes the list.
  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  const results = state.status === "ready" ? state.results : [];
  const showList = open && searchable;

  function change(value: string) {
    setText(value);
    setActive(-1);
    setOpen(true);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      change("");
    } else if (event.key === "ArrowDown" && results.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp" && results.length > 0) {
      event.preventDefault();
      setActive((index) => (index <= 0 ? results.length - 1 : index - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const chosen = showList ? results[active] : undefined;
      if (chosen) navigate(`/lessons/${chosen.lesson_id}`, { state: { from: "search" } });
    }
  }

  return (
    <div
      ref={box}
      className="relative"
      // Tabbing out of the bar and its list closes it, as selecting elsewhere does.
      onBlur={(event) => {
        if (!box.current?.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <label className="sr-only" htmlFor={`${listId}-input`}>
        Search lessons
      </label>
      <Search
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle"
        aria-hidden
      />
      <input
        id={`${listId}-input`}
        type="search"
        value={text}
        onChange={(event) => change(event.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder="Search lessons, e.g. chope"
        autoComplete="off"
        enterKeyHint="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
        className={cn(
          "h-11 w-full rounded-lg border border-line bg-white pr-3 pl-9 text-sm text-ink placeholder:text-subtle",
          "outline-none transition-colors focus:border-ink focus:ring-2 focus:ring-ink/10",
        )}
      />

      {/* Read out as the results change, whether or not the list is open. */}
      <p className="sr-only" aria-live="polite">
        {showList && state.status === "ready" && resultCount(results.length)}
      </p>

      {showList && (
        <div className="absolute inset-x-0 top-full z-20 mt-1.5 max-h-80 overflow-y-auto rounded-lg border border-line bg-white shadow-lg">
          {state.status === "loading" && (
            <div className="flex justify-center py-4 text-brand">
              <Spinner label="Searching" />
            </div>
          )}

          {state.status === "error" && (
            <div className="flex items-center justify-between gap-3 px-3.5 py-3 text-sm">
              <span className="text-danger">{state.message}</span>
              <button
                type="button"
                onClick={retry}
                className="shrink-0 rounded-sm font-semibold text-ink underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                Try again
              </button>
            </div>
          )}

          {state.status === "ready" && results.length === 0 && (
            <p className="px-3.5 py-3 text-sm text-muted">No results available.</p>
          )}

          {/* The listbox stays in the page while open, so aria-controls always points at it. */}
          <ul
            id={listId}
            role="listbox"
            aria-label="Lessons found"
            className="divide-y divide-line"
          >
            {results.map((result, index) => (
              <li key={result.lesson_id} role="presentation">
                <ResultRow
                  id={optionId(index)}
                  result={result}
                  query={query}
                  active={index === active}
                  onHover={() => setActive(index)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ResultRow({
  id,
  result,
  query,
  active,
  onHover,
}: {
  id: string;
  result: SearchResult;
  query: string;
  active: boolean;
  onHover: () => void;
}) {
  const { lesson_id, title, topic_name, completed, snippet } = result;
  const status = completed ? "Completed" : "Not completed";

  return (
    <Link
      id={id}
      to={`/lessons/${lesson_id}`}
      // The lesson steps back here when it closes, so these results are still showing (AC3).
      state={{ from: "search" }}
      role="option"
      aria-selected={active}
      aria-label={`${title}, in ${topic_name}. ${status}.`}
      // The bar keeps focus while arrow keys move through the list; a pointer can still
      // select a row.
      tabIndex={-1}
      onMouseEnter={onHover}
      className={cn(
        "flex items-start gap-3 px-3.5 py-3 transition-colors hover:bg-brand-soft/40",
        active && "bg-brand-soft/60",
      )}
    >
      {completed ? (
        <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-brand text-white">
          <Check className="size-3.5" strokeWidth={3} aria-hidden />
        </span>
      ) : (
        <span className="mt-0.5 size-5 shrink-0 rounded-full border-2 border-line" aria-hidden />
      )}
      <span className="flex min-w-0 flex-1 flex-col" aria-hidden>
        <span className="text-sm font-semibold text-ink">
          <Highlight text={title} query={query} />
        </span>
        <span className="text-caption text-subtle">
          {topic_name} · <span className={cn(completed && "text-brand")}>{status}</span>
        </span>
        {snippet && (
          <span className="mt-0.5 text-caption text-muted">
            <Highlight text={snippet} query={query} />
          </span>
        )}
      </span>
    </Link>
  );
}

/** `text` with every case-insensitive occurrence of `query` marked. */
function Highlight({ text, query }: { text: string; query: string }) {
  const needle = query.toLowerCase();
  const lower = text.toLowerCase();
  const parts: { text: string; match: boolean }[] = [];
  let from = 0;
  for (let at = lower.indexOf(needle); needle && at >= 0; at = lower.indexOf(needle, from)) {
    if (at > from) parts.push({ text: text.slice(from, at), match: false });
    parts.push({ text: text.slice(at, at + needle.length), match: true });
    from = at + needle.length;
  }
  if (from < text.length) parts.push({ text: text.slice(from), match: false });

  return parts.map((part, index) =>
    part.match ? (
      <mark key={index} className="rounded-[2px] bg-brand-soft px-0.5 font-semibold text-ink">
        {part.text}
      </mark>
    ) : (
      <Fragment key={index}>{part.text}</Fragment>
    ),
  );
}

function resultCount(count: number): string {
  if (count === 0) return "No results available.";
  return count === 1 ? "1 result" : `${count} results`;
}
