import { Spinner } from "@sgjio/ui";
import { BLANK_TOKEN, hasBlank, type Asset, type Card, type Issue } from "@sgjio/ui/lesson";
import { Copy, HelpCircle, RectangleHorizontal, Trash2, type LucideIcon } from "lucide-react";
import type { ClipboardEvent } from "react";

import { newQuestion } from "../../lib/cards";
import { CARD_WORD_LIMIT, MAX_CARD_TEXT } from "../../lib/lessons";
import { MarkdownField } from "../MarkdownField";
import { isImageFile, useUpload } from "../../lib/media";
import { AudioField, ImageField } from "./MediaFields";
import { QuestionEditor } from "./QuestionEditor";

/**
 * One card, being written (SCRUM-19): its image and audio, its text, and its question.
 * Pasting an image anywhere on the card (say, copied from an image generator) uploads it as
 * the card's image.
 */
export function CardEditor({
  card,
  index,
  total,
  assets,
  issues,
  onChange,
  onAsset,
  onDuplicate,
  onDelete,
}: {
  card: Card;
  index: number;
  total: number;
  assets: Record<string, Asset>;
  /** This card's issues. */
  issues: Issue[];
  onChange: (change: Partial<Card>) => void;
  /** A file was uploaded: the editor keeps it, so the card can show it at once. */
  onAsset: (asset: Asset) => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const blank = hasBlank(card.text);
  const issueFor = (field: string) => issues.find((issue) => issue.field === field);
  const textIssue = issues.find((issue) => issue.field === "text" && issue.severity === "blocker");
  const pasted = useUpload((asset) => {
    if (asset.kind !== "image") return;
    onAsset(asset);
    onChange({ image: { asset_id: asset.id, alt: card.image?.alt ?? "" } });
  });

  function handlePaste(event: ClipboardEvent) {
    const file = Array.from(event.clipboardData.files).find(isImageFile);
    if (!file) return;
    event.preventDefault();
    void pasted.upload(file);
  }

  return (
    <div onPaste={handlePaste} className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-bold tracking-wide text-muted uppercase">
          Card {index + 1} <span className="font-normal">of {total}</span>
        </h2>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={onDuplicate}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm px-2.5 text-xs font-semibold text-muted hover:bg-white hover:text-ink"
          >
            <Copy className="size-3.5" aria-hidden />
            Duplicate
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm px-2.5 text-xs font-semibold text-muted hover:bg-white hover:text-danger"
          >
            <Trash2 className="size-3.5" aria-hidden />
            Delete card
          </button>
        </div>
      </div>

      <section aria-label="Image and audio" className="grid gap-3 xl:grid-cols-2">
        <ImageField
          image={card.image}
          asset={card.image ? assets[card.image.asset_id] : undefined}
          issue={issueFor("image")}
          onChange={(image, asset) => {
            if (asset) onAsset(asset);
            onChange({ image });
          }}
        />
        <AudioField
          audio={card.audio}
          asset={card.audio ? assets[card.audio.asset_id] : undefined}
          issue={issueFor("audio")}
          onChange={(audio, asset) => {
            if (asset) onAsset(asset);
            onChange({ audio });
          }}
        />
      </section>
      {pasted.uploading && (
        <p className="flex items-center gap-2 text-xs text-muted">
          <Spinner className="size-3.5 text-brand" /> Uploading the pasted image…
        </p>
      )}
      {pasted.error && <p className="text-xs text-danger">{pasted.error}</p>}

      <MarkdownField
        label="Text"
        value={card.text}
        onChange={(text) => onChange({ text })}
        rows={card.question ? 3 : 5}
        blank
        wordLimit={CARD_WORD_LIMIT}
        maxLength={MAX_CARD_TEXT}
        error={textIssue?.message}
        placeholder={
          card.question
            ? "The question, or a sentence with a {{blank}} to fill"
            : "One idea per card. Use **bold** for key words and *italics* for Singlish."
        }
        hint="Bold reads as a highlighter; italics are for Singlish and Malay words."
      />

      {card.question ? (
        <QuestionEditor
          question={card.question}
          hasBlank={blank}
          issues={issues}
          onChange={(change) => onChange({ question: { ...card.question!, ...change } })}
          onRemove={() => onChange({ question: null })}
        />
      ) : (
        <section
          aria-labelledby={`check-${card.id}`}
          className="@container flex flex-col gap-2 rounded-lg border border-dashed border-line p-3"
        >
          <h3 id={`check-${card.id}`} className="text-xs font-semibold text-ink">
            Check understanding
          </h3>
          {/* Side by side when there is room; one per row on a phone. */}
          <div className="grid gap-2 @md:grid-cols-2">
            <QuestionChoice
              icon={RectangleHorizontal}
              title="Add fill-the-blank question"
              hint="Learners fill a gap in the text."
              onClick={() =>
                onChange({
                  question: newQuestion(),
                  text: blank
                    ? card.text
                    : `${card.text.trimEnd()}${card.text.trim() ? " " : ""}${BLANK_TOKEN}`,
                })
              }
            />
            <QuestionChoice
              icon={HelpCircle}
              title="Add multiple-choice question"
              hint="Learners pick from up to 4 answers."
              onClick={() => onChange({ question: newQuestion(4) })}
            />
          </div>
        </section>
      )}
    </div>
  );
}

/** One kind of question a card can add, with what it asks the learner to do. */
function QuestionChoice({
  icon: Icon,
  title,
  hint,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-start gap-2.5 rounded-md bg-white px-3 py-2.5 text-left shadow-sm ring-1 ring-line hover:ring-ink/30 focus-visible:outline-2 focus-visible:outline-brand"
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
      <span className="flex flex-col gap-0.5">
        <span className="text-xs font-semibold text-ink">{title}</span>
        <span className="text-xs text-muted">{hint}</span>
      </span>
    </button>
  );
}
