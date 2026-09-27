import { cn } from "../lib/cn";

/**
 * A topic's progress circle from the Figma home screen (SCRUM-43).
 *
 * Three looks, matching the criteria:
 * - nothing completed: an empty grey ring (AC4)
 * - partly done: a brand-red arc over the grey ring, sized by completed / available (AC2)
 * - everything done: a solid red disc, so a finished topic reads differently at a glance
 *   rather than only as a ring that happens to be closed (AC5)
 *
 * The count sits inside the ring (AC3). The whole thing is aria-hidden: the caller wraps
 * it in something that carries the topic name and the figure as one label, which reads
 * far better than a screen reader spelling out the SVG.
 */
export function ProgressRing({
  completed,
  available,
  size = 56,
  strokeWidth = 5,
  className,
}: {
  completed: number;
  available: number;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const isComplete = available > 0 && completed >= available;
  // Guard against a divide by zero, and against a stale count exceeding the published
  // lessons: the API prevents that (SCRUM-16 AC8), but the arc should never overshoot.
  const fraction = available > 0 ? Math.min(completed / available, 1) : 0;

  const centre = size / 2;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      aria-hidden
      className={cn("shrink-0", className)}
    >
      {isComplete ? (
        <circle cx={centre} cy={centre} r={centre} className="fill-brand" />
      ) : (
        <>
          <circle
            cx={centre}
            cy={centre}
            r={radius}
            strokeWidth={strokeWidth}
            className="fill-none stroke-line"
          />
          {fraction > 0 && (
            <circle
              cx={centre}
              cy={centre}
              r={radius}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - fraction)}
              // Start the arc at the top rather than at 3 o'clock.
              transform={`rotate(-90 ${centre} ${centre})`}
              className="fill-none stroke-brand transition-[stroke-dashoffset] duration-500"
            />
          )}
        </>
      )}

      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        className={cn("text-[11px] font-bold", isComplete ? "fill-white" : "fill-ink")}
      >
        {completed} / {available}
      </text>
    </svg>
  );
}
