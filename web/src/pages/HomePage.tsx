import { Placeholder, useAuth } from "@sgjio/ui";

/** Landing page. The real content arrives with SCRUM-43 and SCRUM-6. */
export function HomePage() {
  const { user } = useAuth();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm font-medium text-muted">Welcome back,</p>
        <h1 className="text-[22px] font-bold text-ink">{user?.name}</h1>
      </div>

      <Placeholder story="SCRUM-43" title="Your progress">
        One circle per topic, filled by lessons completed out of lessons available, plus the overall
        figure. Design: the home-screen frame in Figma.
      </Placeholder>

      <Placeholder story="SCRUM-6" title="Suggested for you">
        The next lesson, drawn from the topic where progress is weakest.
      </Placeholder>
    </div>
  );
}
