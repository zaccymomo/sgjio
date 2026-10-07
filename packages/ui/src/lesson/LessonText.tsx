import type { ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";

import { cn } from "../lib/cn";

/** The elements a card's Markdown may produce. Anything else (headings, images, links,
 * code, raw HTML) is dropped, keeping its text. */
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "br", "blank-slot"];

type MdNode = { type: string; value?: string; children?: MdNode[]; data?: { hName?: string } };

/**
 * A remark plugin that turns {{blank}} into a `blank-slot` element, wherever it sits: in a
 * paragraph, in italics, in a list.
 */
function remarkBlank() {
  const pattern = /\{\{\s*blank\s*\}\}/g;
  const walk = (node: MdNode) => {
    if (!node.children) return;
    node.children = node.children.flatMap((child) => {
      if (child.type !== "text" || !child.value || !pattern.test(child.value)) {
        walk(child);
        return [child];
      }
      pattern.lastIndex = 0;
      const parts: MdNode[] = [];
      child.value.split(pattern).forEach((text, n) => {
        if (n > 0) parts.push({ type: "blank", data: { hName: "blank-slot" } });
        if (text) parts.push({ type: "text", value: text });
      });
      return parts;
    });
  };
  return (tree: MdNode) => walk(tree);
}

/**
 * A card's text: Markdown limited to bold, italics and lists, with the blank drawn by
 * `renderBlank` (the question's answer slot). Bold reads as a highlighter mark, the way key
 * words are marked in a textbook; italics are for Singlish and Malay words.
 */
export function LessonText({
  text,
  renderBlank,
  className,
}: {
  text: string;
  renderBlank?: () => ReactNode;
  className?: string;
}) {
  const components = {
    p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
    strong: ({ children }) => (
      <strong className="rounded-[3px] bg-[linear-gradient(transparent_58%,rgb(254_205_211/0.85)_58%)] px-0.5 font-semibold text-ink">
        {children}
      </strong>
    ),
    em: ({ children }) => <em className="font-medium text-ink italic">{children}</em>,
    ul: ({ children }) => <ul className="mb-3 list-disc space-y-1.5 pl-5 last:mb-0">{children}</ul>,
    ol: ({ children }) => (
      <ol className="mb-3 list-decimal space-y-1.5 pl-5 last:mb-0">{children}</ol>
    ),
    li: ({ children }) => <li className="pl-1 marker:text-brand">{children}</li>,
    "blank-slot": () =>
      renderBlank ? (
        renderBlank()
      ) : (
        <span className="mx-0.5 inline-block h-[1.2em] w-16 translate-y-[0.2em] rounded-md border-2 border-dashed border-subtle" />
      ),
  } as Components;

  return (
    <div className={cn("text-pretty", className)}>
      <Markdown
        remarkPlugins={[remarkBlank]}
        allowedElements={ALLOWED}
        unwrapDisallowed
        skipHtml
        components={components}
      >
        {text}
      </Markdown>
    </div>
  );
}
