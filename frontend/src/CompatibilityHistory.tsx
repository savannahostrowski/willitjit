import { useState } from "react";

import type {
  CompatibilityHistory as History,
  CompatibilitySeries,
} from "./types";

const WIDTH = 900;
const HEIGHT = 300;
const LEFT = 54;
const RIGHT = 24;
const TOP = 24;
const BOTTOM = 48;
const RANGES = [3, 6, 12] as const;

type RangeMonths = (typeof RANGES)[number];

function compatibilityRate(compatible: number, baselineEligible: number) {
  return baselineEligible ? Math.round((compatible / baselineEligible) * 100) : 0;
}

function shortDate(value: string | number) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(value));
}

function axisDate(value: number, rangeMonths: RangeMonths) {
  if (rangeMonths === 12) {
    return new Intl.DateTimeFormat("en", { month: "short", year: "2-digit" }).format(new Date(value));
  }
  return shortDate(value);
}

function fullDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function cohortDate(value: string | null) {
  if (!value) return "legacy cohort";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return value;
  const [, year, month, day] = match;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(Number(year), Number(month) - 1, Number(day))));
}

function seriesLabel(series: CompatibilitySeries) {
  return `Python ${series.pythonSeries} · ${series.packageCount} packages · ${cohortDate(series.datasetUpdated)}`;
}

function dateTime(value: string) {
  return new Date(value).getTime();
}

function cutoffTime(latest: number, months: RangeMonths) {
  const cutoff = new Date(latest);
  cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
  return cutoff.getTime();
}

export function CompatibilityHistory({ history }: { history: History }) {
  const [rangeMonths, setRangeMonths] = useState<RangeMonths>(3);
  const populatedSeries = history.series.filter((series) => series.points.length > 0);
  const latest = Math.max(
    ...populatedSeries.flatMap((series) => series.points.map((point) => dateTime(point.date))),
    0,
  );
  const pythonColors = new Map<string, number>();
  for (const series of populatedSeries) {
    if (!pythonColors.has(series.pythonSeries)) {
      pythonColors.set(series.pythonSeries, pythonColors.size % 4);
    }
  }
  const cutoff = latest ? cutoffTime(latest, rangeMonths) : 0;
  const visibleSeries = populatedSeries
    .map((series) => ({
      ...series,
      colorIndex: pythonColors.get(series.pythonSeries) ?? 0,
      points: series.points.filter((point) => dateTime(point.date) >= cutoff),
    }))
    .filter((series) => series.points.length > 0);
  const visiblePythonSeries = [...new Set(visibleSeries.map((series) => series.pythonSeries))];
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const x = (date: string) => LEFT + ((dateTime(date) - cutoff) / (latest - cutoff)) * plotWidth;
  const y = (percentage: number) => TOP + plotHeight - (percentage / 100) * plotHeight;
  const ticks = [0, 50, 100];
  const xTicks = latest
    ? [cutoff, cutoff + (latest - cutoff) / 2, latest]
    : [];

  return (
    <section className="history-section" id="history">
      <div className="history-copy">
        <h2>JIT compatibility<br />over time</h2>
        <p>
          Each line shows the share of packages with a passing JIT-off baseline
          that also pass with the JIT on across every tested platform.
        </p>
      </div>

      <div className="chart-card">
        {populatedSeries.length > 0 && (
          <div className="chart-toolbar">
            <div className="history-legend" aria-label="History series">
              {visiblePythonSeries.map((pythonSeries) => (
                <span
                  className={`chart-series-${pythonColors.get(pythonSeries) ?? 0}`}
                  key={pythonSeries}
                >
                  <i aria-hidden="true" />
                  Python {pythonSeries}
                </span>
              ))}
            </div>
            <div className="history-range" role="group" aria-label="History range">
              {RANGES.map((months) => (
                <button
                  type="button"
                  aria-pressed={rangeMonths === months}
                  onClick={() => setRangeMonths(months)}
                  key={months}
                >
                  {months === 12 ? "1Y" : `${months}M`}
                </button>
              ))}
            </div>
          </div>
        )}

        {visibleSeries.length > 0 ? (
          <>
            <svg
              className="history-chart"
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              aria-hidden="true"
              focusable="false"
            >
              <title>Package compatibility rate over time</title>
              {ticks.map((tick) => (
                <g key={tick}>
                  <line className="chart-grid" x1={LEFT} x2={WIDTH - RIGHT} y1={y(tick)} y2={y(tick)} />
                  <text className="chart-y-label" x={LEFT - 14} y={y(tick) + 4}>{tick}%</text>
                </g>
              ))}
              {xTicks.map((tick) => (
                <text className="chart-x-label" x={LEFT + ((tick - cutoff) / (latest - cutoff)) * plotWidth} y={HEIGHT - 15} key={tick}>
                  {axisDate(tick, rangeMonths)}
                </text>
              ))}
              {visibleSeries.map((series) => {
                const points = [...series.points].sort((a, b) => a.date.localeCompare(b.date));
                const line = points
                  .map((point) => `${x(point.date)},${y(compatibilityRate(point.compatible, point.baselineEligible))}`)
                  .join(" ");
                return (
                  <g className={`chart-series-${series.colorIndex}`} key={series.id}>
                    {points.length > 1 && <polyline className="chart-series-line" points={line} />}
                    {points.map((point) => {
                      const rate = compatibilityRate(point.compatible, point.baselineEligible);
                      return (
                        <g key={`${series.id}-${point.runId}-${point.date}`}>
                          <circle className="chart-series-point" cx={x(point.date)} cy={y(rate)} r="7" />
                          <text className="chart-value" x={x(point.date)} y={y(rate) - 15}>{rate}%</text>
                        </g>
                      );
                    })}
                  </g>
                );
              })}
            </svg>
            <div className="sr-only">
              <table>
                <caption>JIT compatibility history for the selected time range</caption>
                <thead>
                  <tr>
                    <th scope="col">Series</th>
                    <th scope="col">Date</th>
                    <th scope="col">Python version</th>
                    <th scope="col">Compatible packages</th>
                    <th scope="col">Packages with passing baselines</th>
                    <th scope="col">Surveyed packages</th>
                    <th scope="col">Compatibility rate</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSeries.flatMap((series) => series.points.map((point) => (
                    <tr key={`${series.id}-${point.runId}-${point.date}-accessible`}>
                      <td>{seriesLabel(series)}</td>
                      <td>{fullDate(point.date)}</td>
                      <td>{point.pythonVersion ?? "Not recorded"}</td>
                      <td>{point.compatible}</td>
                      <td>{point.baselineEligible}</td>
                      <td>{point.total}</td>
                      <td>{compatibilityRate(point.compatible, point.baselineEligible)}%</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="chart-placeholder">No completed hosted snapshots in this range.</div>
        )}
      </div>
    </section>
  );
}
