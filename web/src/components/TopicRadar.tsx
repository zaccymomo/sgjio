import { cn } from "@sgjio/ui";

export type RadarTopic = {
  id: string;
  name: string;
  /** 0 to 5. */
  level: number;
  /** The level the aptitude quiz gave the topic, drawn as a dashed outline when shown. */
  quizLevel?: number | null;
};

const LEVELS = [1, 2, 3, 4, 5];
const WIDTH = 360;
const HEIGHT = 290;
const CX = WIDTH / 2;
const CY = HEIGHT / 2;
const RADIUS = 92;
/** Longest line in a spoke's label before it wraps. */
const LINE = 16;

/**
 * A radar of the level in each topic, one spoke per topic on the same 0 to 5 scale
 * (SCRUM-100). The results page draws what the aptitude quiz gave; the Profile tab draws
 * the level reached since, with the quiz's as a dashed outline inside it.
 *
 * The spokes follow the order of the topics given (the order administrators set), so the
 * shape never jumps about between visits. Every level is also written beside its spoke, and
 * the caller lists the topics in text too, so nothing depends on reading the shape. Fewer
 * than three topics make no shape at all, so nothing is drawn.
 */
export function TopicRadar({
  topics,
  showQuiz = false,
  className,
}: {
  topics: RadarTopic[];
  showQuiz?: boolean;
  className?: string;
}) {
  if (topics.length < 3) return null;

  const point = (index: number, level: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / topics.length;
    const distance = (RADIUS * level) / 5;
    return [CX + Math.cos(angle) * distance, CY + Math.sin(angle) * distance] as const;
  };
  const outline = (levelOf: (topic: RadarTopic) => number) =>
    topics.map((topic, index) => point(index, levelOf(topic)).join(",")).join(" ");
  const quizShown = showQuiz && topics.some((topic) => topic.quizLevel != null);

  return (
    <figure className={cn("m-0 flex flex-col items-center gap-2", className)}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full max-w-sm"
        role="img"
        aria-label={`Level in each topic: ${topics
          .map((topic) => `${topic.name}, Level ${topic.level}`)
          .join("; ")}.`}
      >
        {/* The grid: one ring per level, the outermost shaded as the chart's area. */}
        {LEVELS.map((level) => (
          <polygon
            key={level}
            points={topics.map((_, index) => point(index, level).join(",")).join(" ")}
            className={cn("stroke-line", level === 5 ? "fill-surface" : "fill-none")}
            strokeWidth={1}
          />
        ))}
        {topics.map((topic, index) => {
          const [x, y] = point(index, 5);
          return <line key={topic.id} x1={CX} y1={CY} x2={x} y2={y} className="stroke-line" />;
        })}
        {LEVELS.map((level) => {
          const [x, y] = point(0, level);
          return (
            <text key={level} x={x + 4} y={y + 3} className="fill-subtle text-[8px]" aria-hidden>
              {level}
            </text>
          );
        })}

        {quizShown && (
          <polygon
            points={outline((topic) => topic.quizLevel ?? 0)}
            className="fill-none stroke-brand-light"
            strokeWidth={2}
            strokeDasharray="4 3"
            strokeLinejoin="round"
          />
        )}
        <polygon
          points={outline((topic) => topic.level)}
          className="fill-brand/15 stroke-brand"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {topics.map((topic, index) => {
          const [x, y] = point(index, topic.level);
          return (
            <g key={topic.id}>
              <circle cx={x} cy={y} r={3.5} className="fill-white stroke-brand" strokeWidth={2} />
              {/* A larger invisible target, so hovering near a point names it. */}
              <circle cx={x} cy={y} r={10} className="fill-transparent">
                <title>
                  {topic.name}: Level {topic.level}
                  {quizShown && topic.quizLevel != null
                    ? ` (Level ${topic.quizLevel} from your quiz)`
                    : ""}
                </title>
              </circle>
            </g>
          );
        })}

        {topics.map((topic, index) => (
          <SpokeLabel key={topic.id} topic={topic} at={point(index, 6.1)} />
        ))}
      </svg>

      {quizShown && (
        <figcaption className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-2xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-xs border-2 border-brand bg-brand/15" />
            Your level now
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-3.5 border-t-2 border-dashed border-brand-light" />
            From your quiz
          </span>
        </figcaption>
      )}
    </figure>
  );
}

function SpokeLabel({ topic, at: [x, y] }: { topic: RadarTopic; at: readonly [number, number] }) {
  const anchor = Math.abs(x - CX) < 4 ? "middle" : x > CX ? "start" : "end";
  const lines = wrap(topic.name);
  // Labels above the chart grow upwards, those below it downwards, the rest centre on the
  // spoke, so none of them runs into the chart.
  const rows = lines.length + 1;
  const top =
    y < CY - RADIUS ? y - (rows - 1) * 12 : y > CY + RADIUS ? y + 6 : y - ((rows - 1) * 12) / 2 + 3;
  return (
    <text x={x} textAnchor={anchor} className="text-[11px]" aria-hidden>
      {lines.map((line, index) => (
        <tspan key={index} x={x} y={top + index * 12} className="fill-ink font-semibold">
          {line}
        </tspan>
      ))}
      <tspan x={x} y={top + lines.length * 12} className="fill-muted">
        Level {topic.level}
      </tspan>
    </text>
  );
}

/** A topic name on at most two lines, broken between words. */
function wrap(name: string): string[] {
  if (name.length <= LINE) return [name];
  const words = name.split(" ");
  let first = "";
  while (words.length && (first + " " + words[0]).trim().length <= LINE) {
    first = (first + " " + words.shift()).trim();
  }
  if (!first) first = words.shift() ?? "";
  const rest = words.join(" ");
  return rest ? [first, rest.length > LINE + 4 ? `${rest.slice(0, LINE + 2)}…` : rest] : [first];
}
