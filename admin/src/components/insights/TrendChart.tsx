import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

import { percent, type LessonInsights, type TrendSeries } from "../../lib/insights";

export type Metric = "learners" | "average_best" | "right_first_time" | "finish_rate";

const SERIES_KEY: Record<Metric, keyof Omit<TrendSeries, "version">> = {
  learners: "finished",
  average_best: "average_best",
  right_first_time: "right_first_time",
  finish_rate: "finish_rate",
};

const WEEK = new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short" });

/** "2026-10-05" (a Monday, Singapore time) -> "5 Oct". */
function weekLabel(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return WEEK.format(new Date(year, month - 1, day));
}

/** The version being viewed in brand red; the others recede, the one before a little less. */
function versionColor(version: number, shown: number): string {
  if (version === shown) return "var(--color-brand)";
  return version === shown - 1 ? "#fda4af" : "#d1d5db";
}

/**
 * The selected tile's figure week by week, for every version with figures (SCRUM-84): learners
 * finishing it as columns, and the rest as each version's running figure, so a rewrite shows
 * as a step from one line to the next. Weeks with too few learners are gaps.
 */
export function TrendChart({
  trend,
  metric,
  shownVersion,
}: {
  trend: LessonInsights["trend"];
  metric: Metric;
  shownVersion: number;
}) {
  const key = SERIES_KEY[metric];
  const versions = trend.series.map((series) => series.version);
  const rows = trend.weeks.map((week, i) => ({
    week: weekLabel(week),
    ...Object.fromEntries(trend.series.map((s) => [`v${s.version}`, s[key][i]])),
  }));
  const isCount = metric === "learners";
  const format = (value: number) => (isCount ? String(value) : percent(value));

  function TooltipContent({ active, payload, label }: TooltipContentProps<ValueType, NameType>) {
    if (!active || !payload?.length) return null;
    const shown = payload.filter((item) => item.value !== null && item.value !== undefined);
    if (!shown.length) return null;
    return (
      <div className="rounded-md bg-ink px-3 py-2 text-xs text-white shadow-lg">
        <p className="mb-1 font-semibold">Week of {label}</p>
        {shown.map((item) => (
          <p key={item.dataKey as string} className="flex items-center gap-2 tabular-nums">
            <span className="size-2 rounded-full" style={{ background: item.color }} aria-hidden />
            Version {String(item.dataKey).slice(1)}: {format(item.value as number)}
            {isCount && " learners"}
          </p>
        ))}
      </div>
    );
  }

  const axis = { fontSize: 11, fill: "var(--color-subtle)" };
  const common = (
    <>
      <CartesianGrid vertical={false} stroke="var(--color-line)" />
      <XAxis
        dataKey="week"
        tick={axis}
        tickLine={false}
        axisLine={{ stroke: "var(--color-line)" }}
        interval="preserveStartEnd"
        minTickGap={24}
      />
      <Tooltip
        content={TooltipContent}
        cursor={isCount ? { fill: "rgba(17,24,39,0.04)" } : { stroke: "var(--color-line)" }}
      />
    </>
  );

  return (
    <div className="flex flex-col gap-3">
      {versions.length > 1 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Versions">
          {versions.map((version) => (
            <li key={version} className="flex items-center gap-1.5">
              <span
                className="size-2.5 rounded-sm"
                style={{ background: versionColor(version, shownVersion) }}
                aria-hidden
              />
              Version {version}
            </li>
          ))}
        </ul>
      )}
      <div className="h-56 sm:h-72" role="img" aria-label={`${metric} by week, per version`}>
        <ResponsiveContainer width="100%" height="100%">
          {isCount ? (
            <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: -24 }}>
              {common}
              <YAxis tick={axis} tickLine={false} axisLine={false} allowDecimals={false} />
              {versions.map((version) => (
                <Bar
                  key={version}
                  dataKey={`v${version}`}
                  stackId="weeks"
                  fill={versionColor(version, shownVersion)}
                  maxBarSize={28}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          ) : (
            <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              {common}
              <YAxis
                tick={axis}
                tickLine={false}
                axisLine={false}
                domain={[0, 1]}
                ticks={[0, 0.5, 1]}
                tickFormatter={format}
              />
              {versions.map((version) => (
                <Line
                  key={version}
                  dataKey={`v${version}`}
                  type="linear"
                  stroke={versionColor(version, shownVersion)}
                  strokeWidth={version === shownVersion ? 2.5 : 2}
                  dot={{ r: 3, strokeWidth: 0, fill: versionColor(version, shownVersion) }}
                  activeDot={{ r: 5, stroke: "white", strokeWidth: 2 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
