import { Alert, apiFetch, Button, useAuth, type User, type UserType } from "@sgjio/ui";
import {
  Award,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Languages,
  MessageSquare,
  NotebookPen,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

type Screen = {
  icon: LucideIcon;
  title: string;
  body: string;
  /** Small print under the body. */
  note?: string;
};

/** What SGJio does for a Newcomer (SCRUM-94 AC2). */
const NEWCOMER_SCREENS: Screen[] = [
  {
    icon: Sparkles,
    title: "Welcome to SGJio",
    body: "SGJio helps you feel at home in Singapore: the everyday words, habits and unspoken rules that locals take for granted, from Singlish to hawker centres to the office.",
  },
  {
    icon: BookOpen,
    title: "Short lessons and quizzes",
    body: "Each lesson is a few cards you can read in about two minutes, with a question or two to check what stuck. Your home page shows how far you've got in each topic.",
  },
  {
    icon: MessageSquare,
    title: "Practise real situations",
    body: "Try a conversation with an AI partner before you have it for real, like ordering at a hawker stall, chatting with a neighbour or your first day at work.",
  },
  {
    icon: Users,
    title: "Meet a local buddy",
    body: "Get matched with a Singaporean who shares your interests, for a chat over kopi or a walk around their neighbourhood.",
  },
  {
    icon: NotebookPen,
    title: "Your integration passport",
    body: "Your lessons, practice and buddy sessions add up to a record of the effort you've made to settle in. You can refer to it in your PR application.",
    note: "ICA decides PR applications independently. Using SGJio doesn't change your chances or the outcome.",
  },
];

/** What SGJio does for a Singaporean (SCRUM-94 AC3). */
const SINGAPOREAN_SCREENS: Screen[] = [
  {
    icon: Sparkles,
    title: "Welcome to SGJio",
    body: "SGJio connects you with people who have recently moved to Singapore, so you can share what makes this place home and learn about where they come from.",
  },
  {
    icon: Users,
    title: "Be a buddy",
    body: "Meet newcomers who share your interests, over kopi, a hawker meal or a walk around your neighbourhood, and help them find their feet.",
  },
  {
    icon: Languages,
    title: "A cultural exchange",
    body: "It goes both ways. Practise a language with a native speaker, or get tips from someone who knows a place before you travel there.",
  },
  {
    icon: Award,
    title: "Your contributions count",
    body: "Every session you take part in is recorded on your profile, so the time you give to welcoming newcomers is recognised.",
  },
];

/** Accounts without a type (none in practice) see the Newcomer set. */
function screensFor(type: UserType | null | undefined): Screen[] {
  return type === "singaporean" ? SINGAPOREAN_SCREENS : NEWCOMER_SCREENS;
}

/**
 * The introduction shown on first sign-in, before profile setup (SCRUM-94). Finishing or
 * skipping it is recorded, so it isn't shown automatically again (AC6). Settings links here
 * with ?replay=1 to see it again, which records nothing and returns to Settings.
 */
export function IntroPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // Decided once: recording the finish updates the user, which mustn't flip the mode.
  const [replay] = useState(() => params.get("replay") === "1" || Boolean(user?.intro_finished_at));
  const screens = screensFor(user?.user_type);
  const [current, setCurrent] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const last = current === screens.length - 1;
  const screen = screens[current];
  const Icon = screen.icon;

  // Finished or skipped: both lead to profile setup (AC1, AC5).
  const leave = useCallback(async () => {
    if (replay) {
      navigate("/settings", { replace: true });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setUser(await apiFetch<User>("/api/intro/finished", { method: "POST" }));
      navigate("/profile-setup", { replace: true });
    } catch {
      setError("We couldn't save your progress. Check your connection and try again.");
      setSaving(false);
    }
  }, [replay, navigate, setUser]);

  const go = useCallback(
    (to: number) => setCurrent(Math.max(0, Math.min(screens.length - 1, to))),
    [screens.length],
  );

  // The arrow keys move between screens, as in a lesson.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLElement && event.target.closest("input, textarea")) return;
      if (event.key === "ArrowRight") go(current + 1);
      if (event.key === "ArrowLeft") go(current - 1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, go]);

  return (
    <div className="flex min-h-dvh justify-center bg-surface sm:items-center sm:p-6">
      <main
        aria-label="Introduction to SGJio"
        className="flex min-h-dvh w-full flex-col bg-white sm:min-h-0 sm:max-w-[430px] sm:rounded-lg sm:border sm:border-line sm:shadow-sm"
      >
        {/* Top bar: how far through, and Skip (AC4, AC5) */}
        <div className="flex items-center gap-3 px-4 pt-[max(0.875rem,env(safe-area-inset-top))] pb-2">
          <div className="flex flex-1 gap-1" aria-hidden>
            {screens.map((s, n) => (
              <span
                key={s.title}
                className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${
                  n <= current ? "bg-brand" : "bg-ink/10"
                }`}
              />
            ))}
          </div>
          <Button variant="ghost" size="sm" onClick={() => void leave()} disabled={saving}>
            Skip
          </Button>
        </div>

        <section
          key={current}
          aria-live="polite"
          className="flex flex-1 flex-col justify-center gap-5 px-6 py-8 sm:py-12"
        >
          <div className="flex size-16 items-center justify-center rounded-full bg-brand-soft text-brand">
            <Icon className="size-8" aria-hidden />
          </div>
          <div className="space-y-3">
            <p className="text-caption font-medium text-muted">
              {current + 1} of {screens.length}
            </p>
            <h1 className="text-[26px] leading-tight font-bold text-ink">{screen.title}</h1>
            <p className="text-base leading-relaxed text-muted">{screen.body}</p>
            {screen.note && (
              <p className="rounded-md bg-surface p-3 text-sm text-muted">{screen.note}</p>
            )}
          </div>
        </section>

        <div className="space-y-3 px-4 pt-2 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {error && <Alert tone="error">{error}</Alert>}
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => go(current - 1)} disabled={current === 0}>
              <ChevronLeft className="size-4" aria-hidden />
              Back
            </Button>
            {last ? (
              <Button variant="accent" fullWidth onClick={() => void leave()} loading={saving}>
                {replay ? "Done" : "Get started"}
              </Button>
            ) : (
              <Button variant="primary" fullWidth onClick={() => go(current + 1)}>
                Next
                <ChevronRight className="size-4" aria-hidden />
              </Button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
