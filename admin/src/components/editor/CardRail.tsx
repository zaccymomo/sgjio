import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn } from "@sgjio/ui";
import type { Asset, Card, Issue } from "@sgjio/ui/lesson";
import {
  ArrowDown,
  ArrowUp,
  Copy,
  HelpCircle,
  Mic,
  Plus,
  RectangleHorizontal,
  Trash2,
  Type,
} from "lucide-react";

import { cardLabel, type Preset } from "../../lib/cards";
import { DragHandle } from "../DragHandle";
import { RowMenu } from "../RowMenu";
import { SortableList } from "../SortableList";

function Thumbnail({ card, asset }: { card: Card; asset: Asset | undefined }) {
  if (card.image && asset) {
    return (
      <span
        className="relative block h-9 w-12 shrink-0 overflow-hidden rounded-sm"
        style={{
          background: asset.color ? `color-mix(in srgb, ${asset.color} 18%, white)` : undefined,
        }}
      >
        <img src={asset.url} alt="" className="h-full w-full object-contain" draggable={false} />
      </span>
    );
  }
  const Icon = card.question ? HelpCircle : card.audio ? Mic : Type;
  return (
    <span
      className={cn(
        "flex h-9 w-12 shrink-0 items-center justify-center rounded-sm",
        card.question ? "bg-brand-soft text-brand" : "bg-surface text-subtle",
      )}
    >
      <Icon className="size-4" aria-hidden />
    </span>
  );
}

/**
 * The deck down the editor's left side (SCRUM-19): one row per card, selected to edit it.
 * Cards are reordered by dragging, by keyboard on the handle, or with Move up and down in
 * a card's menu. A dot marks a card with something to fix (red) or worth a look (amber).
 */
export function CardRail({
  cards,
  assets,
  issues,
  selectedId,
  onSelect,
  onReorder,
  onAdd,
  onDuplicate,
  onDelete,
}: {
  cards: Card[];
  assets: Record<string, Asset>;
  issues: Issue[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onReorder: (ids: string[]) => void;
  onAdd: (preset: Preset) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const severity = (id: string) => {
    const mine = issues.filter((issue) => issue.card_id === id);
    if (mine.some((issue) => issue.severity === "blocker")) return "blocker";
    if (mine.length) return "warning";
    return null;
  };

  return (
    <nav aria-label="Cards" className="flex flex-col gap-2">
      <SortableList
        items={cards}
        getId={(card) => card.id}
        getLabel={(card) => `card ${cards.indexOf(card) + 1}`}
        disabled={false}
        onReorder={(ids) => onReorder(ids)}
        className="flex flex-col gap-1"
        renderItem={(card, reorder) => {
          const n = cards.indexOf(card);
          const selected = card.id === selectedId;
          const flag = severity(card.id);
          return (
            <div
              className={cn(
                "group flex items-center gap-1 rounded-md border bg-white pr-0.5 transition-colors",
                selected ? "border-ink shadow-sm" : "border-transparent hover:border-line",
              )}
            >
              <DragHandle reorder={reorder} />
              <button
                type="button"
                onClick={() => onSelect(card.id)}
                aria-current={selected ? "true" : undefined}
                className="flex min-w-0 flex-1 items-center gap-2 py-1.5 text-left focus-visible:outline-2 focus-visible:outline-brand"
              >
                <span className="relative">
                  <Thumbnail
                    card={card}
                    asset={card.image ? assets[card.image.asset_id] : undefined}
                  />
                  {flag && (
                    <span
                      className={cn(
                        "absolute -top-1 -right-1 size-2.5 rounded-full ring-2 ring-white",
                        flag === "blocker" ? "bg-danger" : "bg-amber-400",
                      )}
                      aria-label={
                        flag === "blocker" ? "Needs fixing before publishing" : "Worth a look"
                      }
                    />
                  )}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="text-2xs font-bold text-subtle">
                    {n + 1}
                    {card.question &&
                      (card.question.options.length >= 2 ? " · Question" : " · Tap")}
                    {card.audio && " · Audio"}
                  </span>
                  <span className="line-clamp-2 text-xs leading-snug text-ink">
                    {cardLabel(card)}
                  </span>
                </span>
              </button>
              <RowMenu
                name={`card ${n + 1}`}
                moveKey={reorder.moveKey}
                groups={[
                  [
                    { label: "Duplicate", icon: Copy, onSelect: () => onDuplicate(card.id) },
                    {
                      label: "Move up",
                      icon: ArrowUp,
                      onSelect: () => reorder.moveUp?.(),
                      disabled: !reorder.moveUp,
                    },
                    {
                      label: "Move down",
                      icon: ArrowDown,
                      onSelect: () => reorder.moveDown?.(),
                      disabled: !reorder.moveDown,
                    },
                  ],
                  [
                    {
                      label: "Delete",
                      icon: Trash2,
                      onSelect: () => onDelete(card.id),
                      danger: true,
                    },
                  ],
                ]}
              />
            </div>
          );
        }}
        renderOverlay={(card) => (
          <div className="flex items-center gap-2 rounded-md border border-ink bg-white p-1.5 shadow-lg">
            <Thumbnail card={card} asset={card.image ? assets[card.image.asset_id] : undefined} />
            <span className="line-clamp-2 text-xs text-ink">{cardLabel(card)}</span>
          </div>
        )}
      />

      <DropdownMenu.Root modal={false}>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            className="flex h-10 items-center justify-center gap-1.5 rounded-md border border-dashed border-line text-sm font-semibold text-muted hover:border-ink/40 hover:text-ink data-[state=open]:border-ink/40 data-[state=open]:text-ink"
          >
            <Plus className="size-4" aria-hidden />
            Add card
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="start"
            sideOffset={4}
            className="z-50 min-w-56 rounded-md border border-line bg-white p-1 shadow-lg"
          >
            {(
              [
                {
                  preset: "story",
                  label: "Story card",
                  hint: "Text, with an image or audio",
                  icon: Type,
                },
                {
                  preset: "question",
                  label: "Question card",
                  hint: "A sentence with a blank to fill",
                  icon: RectangleHorizontal,
                },
              ] as const
            ).map(({ preset, label, hint, icon: Icon }) => (
              <DropdownMenu.Item
                key={preset}
                onSelect={() => onAdd(preset)}
                className="flex cursor-pointer items-start gap-2.5 rounded-sm px-2.5 py-2 outline-none data-[highlighted]:bg-surface"
              >
                <Icon className="mt-0.5 size-4 text-muted" aria-hidden />
                <span className="flex flex-col">
                  <span className="text-sm font-semibold text-ink">{label}</span>
                  <span className="text-xs text-muted">{hint}</span>
                </span>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </nav>
  );
}
