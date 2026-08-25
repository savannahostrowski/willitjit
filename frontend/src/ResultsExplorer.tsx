import { Fragment, useMemo, useState } from "react";

import type { Condition, Observation, Snapshot, Status } from "./types";

const statusMarks: Record<Status, string> = {
  compatible: "✓",
  "needs-triage": "!",
  "baseline-blocked": "−",
  "infrastructure-failure": "×",
  "not-tested": "·",
};

const statusLabels: Record<Status, string> = {
  compatible: "JIT compatible",
  "needs-triage": "Needs JIT triage",
  "baseline-blocked": "Baseline failed",
  "infrastructure-failure": "Setup failed",
  "not-tested": "Not tested",
};

type StatusFilter = Status | "all";

const filters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "compatible", label: "Compatible" },
  { value: "needs-triage", label: "Needs triage" },
  { value: "baseline-blocked", label: "Baseline failed" },
  { value: "infrastructure-failure", label: "Setup failed" },
  { value: "not-tested", label: "Not tested" },
];

const compactNumber = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2,
});

function conditionLabel(condition: Condition) {
  if (!condition) return "Not run";
  if (condition.timedOut) return "Timed out";
  return condition.returnCode === 0 ? "Passed" : `Exited ${condition.returnCode}`;
}

function elapsedLabel(seconds: number) {
  if (seconds < 1) return `${seconds.toFixed(2)}s`;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

function hasPassingBaseline(item: Snapshot["packages"][number], platforms: string[]) {
  if (item.baselineEligible !== undefined) return item.baselineEligible;
  return platforms.every((platform) => {
    const baseline = item.platforms[platform]?.baseline;
    return baseline?.returnCode === 0 && !baseline.timedOut;
  });
}

function ConditionResult({ condition, label }: { condition: Condition; label: string }) {
  return (
    <td data-label={label}>
      <strong>{conditionLabel(condition)}</strong>
      {condition
        ? (
          <small>
            {condition.suiteSummary}
            <span className="runner-time">Runner time: {elapsedLabel(condition.elapsedSeconds)}</span>
          </small>
        )
        : <small>No result captured.</small>}
    </td>
  );
}

function FailureEvidence({ observation }: { observation: Observation }) {
  const failures = [
    ["JIT off", observation.baseline?.failureExcerpt],
    ["JIT on", observation.jit?.failureExcerpt],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  if (
    observation.status === "compatible"
    || observation.status === "not-tested"
    || (failures.length === 0 && !observation.explanation)
  ) {
    return null;
  }

  return (
    <tr className="evidence-issue">
      <td colSpan={4}>
        <p>{observation.explanation}</p>
        {failures.map(([label, excerpt]) => (
          <div key={label}>
            <span>{label} excerpt</span>
            <code>{excerpt}</code>
          </div>
        ))}
      </td>
    </tr>
  );
}

export function ResultsExplorer({ snapshot }: { snapshot: Snapshot }) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const compatible = snapshot.summary.packages.compatible ?? 0;
  const baselineEligible = snapshot.summary.baselineEligible ?? snapshot.packages.filter(
    (item) => hasPassingBaseline(item, snapshot.run.expectedPlatforms),
  ).length;
  const compatibilityRate = baselineEligible
    ? Math.round((compatible / baselineEligible) * 100)
    : 0;
  const pending = snapshot.run.completedObservations === 0;
  const cpythonVersion = snapshot.run.github?.cpythonVersion ?? "3.14.6";
  const cpythonLabel = cpythonVersion.replace(".0rc", " RC").toUpperCase();
  const githubRepository = snapshot.run.github?.repository;
  const githubRunId = snapshot.run.github?.runId;
  const githubRunUrl = githubRepository
    && /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(githubRepository)
    && githubRunId
    && /^\d+$/.test(githubRunId)
    ? `https://github.com/${githubRepository}/actions/runs/${githubRunId}`
    : null;
  const statusCounts = useMemo(() => {
    const counts = Object.fromEntries(filters.map(({ value }) => [value, 0])) as Record<StatusFilter, number>;
    counts.all = snapshot.packages.length;
    for (const item of snapshot.packages) counts[item.overallStatus] += 1;
    return counts;
  }, [snapshot.packages]);
  const visiblePackages = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return snapshot.packages.filter((item) => (
      (statusFilter === "all" || item.overallStatus === statusFilter)
      && (!normalizedQuery || item.name.toLocaleLowerCase().includes(normalizedQuery))
    ));
  }, [query, snapshot.packages, statusFilter]);

  return (
    <section className="results-section" id="results">
      <div className="checklist-heading">
        <div>
          <h1>Will It JIT?</h1>
          <p>Testing CPython JIT compatibility across the top PyPI packages.</p>
        </div>
        <div
          className="compatibility-summary"
          aria-label={pending
            ? `Awaiting the CPython ${cpythonLabel} survey`
            : `${compatible} of ${baselineEligible} packages with passing baselines are JIT compatible. ${baselineEligible} of ${snapshot.run.targetPackages} packages had passing baselines.`}
        >
          <span>{pending ? "Target" : "Latest survey"}</span>
          <strong>
            {pending ? cpythonLabel : compatibilityRate}
            {!pending && <small>%</small>}
          </strong>
          <p>{pending ? "survey pending" : `${compatible} of ${baselineEligible} JIT compatible`}</p>
          {!pending && (
            <small className="summary-coverage">
              {baselineEligible} of {snapshot.run.targetPackages} had passing baselines
            </small>
          )}
          {githubRunUrl && (
            <a
              className="summary-run-link"
              href={githubRunUrl}
              target="_blank"
              rel="noreferrer"
              aria-label="View the GitHub Actions run used for these results"
            >
              View CI run <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
      </div>

      <div className="results-controls">
        <div className="status-filters" role="group" aria-label="Filter packages by result">
          {filters.map(({ value, label }) => (
            <button
              className="status-filter"
              type="button"
              aria-pressed={statusFilter === value}
              key={value}
              onClick={() => setStatusFilter(value)}
            >
              <span>{label}</span>
              <small>{statusCounts[value]}</small>
            </button>
          ))}
        </div>
        <label className="mobile-status-filter">
          <span>Result</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
          >
            {filters.map(({ value, label }) => (
              <option value={value} key={value}>{label} ({statusCounts[value]})</option>
            ))}
          </select>
        </label>
        <label className="package-search">
          <span className="sr-only">Search packages</span>
          <input
            type="search"
            value={query}
            placeholder="Search packages"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>
      <p className="sr-only" aria-live="polite">
        Showing {visiblePackages.length} of {snapshot.packages.length} packages.
      </p>

      <div className="checklist" aria-label="Package compatibility results">
        {visiblePackages.map((item) => {
          const observations = snapshot.run.expectedPlatforms.map((platform) => ({
            name: platform,
            observation: item.platforms[platform],
          }));
          const commands = [...new Set(
            observations.flatMap(({ observation }) => observation.command ? [observation.command] : []),
          )];

          return (
            <details className={`checklist-item ${item.overallStatus}`} key={item.name}>
            <summary>
              <span className="check-mark" aria-hidden="true">{statusMarks[item.overallStatus]}</span>
              <span className="package-title">
                <b>{item.name}</b>
                <span className="package-subline">
                  <small className="package-status">{statusLabels[item.overallStatus]}</small>
                  <small
                    className="package-meta"
                    title={`${item.downloads.toLocaleString("en-US")} downloads in 30 days`}
                  >
                    Rank {item.rank} · {compactNumber.format(item.downloads)} downloads / 30d
                  </small>
                </span>
              </span>
              <span className="platform-checks" aria-label="Platform statuses">
                {snapshot.run.expectedPlatforms.map((platform) => {
                  const status = item.platforms[platform]?.status ?? "not-tested";
                  return (
                    <span className={status} key={platform} title={statusLabels[status]}>
                      <b aria-hidden="true">{statusMarks[status]}</b>
                      {platform}
                      <span className="sr-only">: {statusLabels[status]}</span>
                    </span>
                  );
                })}
              </span>
              <span className="expand" aria-hidden="true">+</span>
            </summary>
            <div className="package-evidence" role="region" aria-label={`${item.name} run evidence`}>
              <div className="evidence-table-wrap">
                <table className="evidence-table">
                  <caption className="sr-only">{item.name} results by platform</caption>
                  <thead>
                    <tr>
                      <th scope="col">Platform</th>
                      <th scope="col">JIT off</th>
                      <th scope="col">JIT on</th>
                      <th scope="col">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {observations.map(({ name, observation }) => (
                      <Fragment key={name}>
                        <tr className={`evidence-result ${observation.status}`}>
                          <th scope="row">
                            <span>{name}</span>
                            <small>
                              <i aria-hidden="true">{statusMarks[observation.status]}</i>
                              {observation.label}
                            </small>
                          </th>
                          <ConditionResult condition={observation.baseline} label="JIT off" />
                          <ConditionResult condition={observation.jit} label="JIT on" />
                          <td data-label="Source">
                            {observation.revision
                              ? (
                                <a
                                  href={`${item.repository}/commit/${observation.revision}`}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {observation.revision.slice(0, 9)} ↗
                                </a>
                              )
                              : <small>Not available</small>}
                          </td>
                        </tr>
                        <FailureEvidence observation={observation} />
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
              {commands.length > 0 && (
                <div className="evidence-commands">
                  <span>{commands.length === 1 ? "Test command" : "Test commands"}</span>
                  {commands.map((command) => <code key={command}>{command}</code>)}
                </div>
              )}
            </div>
            </details>
          );
        })}
        {visiblePackages.length === 0 && (
          <div className="empty-results">
            <strong>No packages found.</strong>
            <button type="button" onClick={() => { setQuery(""); setStatusFilter("all"); }}>
              Clear filters
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
