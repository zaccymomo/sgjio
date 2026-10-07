import { Spinner } from "@sgjio/ui";
import { BLANK_TOKEN, hasBlank, type Asset, type Card, type Issue } from "@sgjio/ui/lesson";
import { Copy, HelpCircle, RectangleHorizontal, Trash2 } from "lucide-react";
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
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-line p-3">
          <span className="text-xs text-muted">Check understanding:</span>
          <button
            type="button"
            onClick={() =>
              onChange({
                question: newQuestion(),
                text: blank
                  ? card.text
                  : `${card.text.trimEnd()}${card.text.trim() ? " " : ""}${BLANK_TOKEN}`,
              })
            }
            className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-white px-2.5 text-xs font-semibold text-ink shadow-sm ring-1 ring-line hover:ring-ink/30"
          >
            <RectangleHorizontal className="size-3.5" aria-hidden />
            Add fill-the-blank question
          </button>
          <button
            type="button"
            onClick={() => onChange({ question: newQuestion(4) })}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-white px-2.5 text-xs font-semibold text-ink shadow-sm ring-1 ring-line hover:ring-ink/30"
          >
            <HelpCircle className="size-3.5" aria-hidden />
            Add multiple-choice question
          </button>
        </div>
      )}
    </div>
  );
}
