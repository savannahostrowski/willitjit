import type { CompatibilityHistory as History } from "./types";

const WIDTH = 900;
const HEIGHT = 300;
const LEFT = 54;
const RIGHT = 24;
const TOP = 24;
const BOTTOM = 48;

function compatibilityRate(compatible: number, total: number) {
  return total ? Math.round((compatible / total) * 100) : 0;
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(value));
}

export function CompatibilityHistory({ history }: { history: History }) {
  const points = [...history.points].sort((a, b) => a.date.localeCompare(b.date));
  const latest = points.at(-1);
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const x = (index: number) => points.length === 1
    ? LEFT + plotWidth / 2
    : LEFT + (index / Math.max(1, points.length - 1)) * plotWidth;
  const y = (percentage: number) => TOP + plotHeight - (percentage / 100) * plotHeight;
  const compatibleLine = points
    .map((point, index) => `${x(index)},${y(compatibilityRate(point.compatible, point.total))}`)
    .join(" ");
  const ticks = [0, 50, 100];
  const latestRate = latest ? compatibilityRate(latest.compatible, latest.total) : 0;

  return (
    <section className="history-section" id="history">
      <div className="history-copy">
        <h2>Compatibility<br />history.</h2>
        <p>{history.definition}</p>
        {!latest && (
          <p className="history-empty">The first completed hosted survey will start this chart.</p>
        )}
      </div>

      <div className="chart-card">
        {points.length ? (
          <>
            <svg
              className="history-chart"
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              role="img"
              aria-label={`${latestRate}% of packages compatible in the latest survey`}
            >
              <title>Package compatibility rate over time</title>
              {ticks.map((tick) => (
                <g key={tick}>
                  <line className="chart-grid" x1={LEFT} x2={WIDTH - RIGHT} y1={y(tick)} y2={y(tick)} />
                  <text className="chart-y-label" x={LEFT - 14} y={y(tick) + 4}>{tick}%</text>
                </g>
              ))}
              {points.length > 1 && <polyline className="chart-compatible" points={compatibleLine} />}
              {points.map((point, index) => {
                const rate = compatibilityRate(point.compatible, point.total);
                return (
                  <g key={`${point.runId}-${point.date}`}>
                    <circle className="chart-compatible-point" cx={x(index)} cy={y(rate)} r="7" />
                    <text className="chart-value" x={x(index)} y={y(rate) - 15}>{rate}%</text>
                    <text className="chart-x-label" x={x(index)} y={HEIGHT - 15}>{shortDate(point.date)}</text>
                  </g>
                );
              })}
            </svg>
            {points.length === 1 && (
              <p className="chart-note">First real cross-platform datapoint. Weekly surveys will extend the line.</p>
            )}
          </>
        ) : (
          <div className="chart-placeholder">No completed hosted snapshots yet.</div>
        )}
      </div>
    </section>
  );
}
