import { Placeholder } from "@sgjio/ui";

/** Tabs whose modules are planned for later sprints. */
export function ComingSoonPage({ title, module }: { title: string; module: string }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[22px] font-bold text-ink">{title}</h1>
      <Placeholder story={module} title="Coming in a later sprint">
        This tab is part of the navigation from the Figma design. Its stories are not in Sprint 1.
      </Placeholder>
    </div>
  );
}
