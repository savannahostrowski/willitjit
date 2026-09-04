import { Fragment, useMemo, useState } from "react";

import type {
  Condition,
  Observation,
  ResultsVersion,
  Runtime,
  RuntimeResult,
  Snapshot,
  Status,
} from "./types";

const statusMarks: Record<Status, string> = {
  compatible: "✓",
  "needs-triage": "!",
  "baseline-blocked": "−",
  "infrastructure-failure": "×",
  "not-tested": "·",
};

const statusLabels: Record<Status, string> = {
  compatible: "Compatible",
  "needs-triage": "Needs triage",
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

const filterDescriptions: Record<StatusFilter, string> = {
  all: "Results compare the same upstream tests with the JIT off and on. Packages without a passing JIT-off baseline are excluded from the compatibility rate.",
  compatible: "JIT compatible means the tests passed with the JIT off and on across every tested platform.",
  "needs-triage": "Needs triage means the tests passed with the JIT off but failed or timed out with it on.",
  "baseline-blocked": "Baseline failed means the JIT-off test run did not pass, so the package does not count against JIT compatibility.",
  "infrastructure-failure": "Setup failed means checkout, environment, or dependency setup did not complete, so no compatibility result was produced.",
  "not-tested": "Not tested means no result was collected for this package and Python version.",
};

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

function compatibilityRate(compatible: number, baselineEligible: number) {
  return baselineEligible ? Math.round((compatible / baselineEligible) * 100) : 0;
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

function FailureEvidence({
  observation,
  baselineLabel,
  targetLabel,
}: {
  observation: Observation;
  baselineLabel: string;
  targetLabel: string;
}) {
  const failures = [
    [baselineLabel, observation.baseline?.failureExcerpt],
    [targetLabel, observation.target?.failureExcerpt],
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

function packageStatusLabel(results: Partial<Record<Runtime, RuntimeResult>>) {
  const status = results.jit?.overallStatus ?? "not-tested";
  if (status === "compatible") return "JIT compatible";
  if (status === "needs-triage") return "Possible JIT regression";
  return statusLabels[status];
}

export function ResultsExplorer({
  snapshot,
  versions,
  activeVersion,
  onVersionChange,
}: {
  snapshot: Snapshot;
  versions: ResultsVersion[];
  activeVersion: string;
  onVersionChange: (version: string) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [evidenceRuntimeByPackage, setEvidenceRuntimeByPackage] = useState<Record<string, Runtime>>({});
  const jitSummary = snapshot.summary.runtimes.jit;
  const compatible = jitSummary?.packages.compatible ?? 0;
  const baselineEligible = jitSummary?.baselineEligible ?? 0;
  const rate = compatibilityRate(compatible, baselineEligible);
  const pending = !jitSummary?.completedObservations;
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
          <p>Testing JIT compatibility across the top PyPI packages.</p>
          <div className="python-versions" role="group" aria-label="Python version">
            {versions.map((version) => (
              <button
                type="button"
                aria-label={`CPython ${version.pythonVersion}`}
                aria-pressed={version.id === activeVersion}
                key={version.id}
                onClick={() => onVersionChange(version.id)}
              >
                <span>{version.id}</span>
                <small>{version.pythonVersion}</small>
              </button>
            ))}
          </div>
        </div>
        <div className="survey-summary">
          <div className="runtime-summaries">
            <div
              className="compatibility-summary"
              aria-label={pending
                ? "JIT results pending"
                : `${compatible} of ${baselineEligible} packages with passing baselines are JIT compatible.`}
            >
              <span>JIT</span>
              <strong>
                {pending ? "Pending" : rate}
                {!pending && <small>%</small>}
              </strong>
              <p>{pending ? "results pending" : `${compatible} of ${baselineEligible} compatible`}</p>
            </div>
          </div>
          {pending && <small className="summary-coverage">Package tests pending</small>}
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
      <p className="filter-description" aria-live="polite">
        {filterDescriptions[statusFilter]}
      </p>
      <p className="sr-only" aria-live="polite">
        Showing {visiblePackages.length} of {snapshot.packages.length} packages.
      </p>

      <div className="checklist" aria-label="Package compatibility results">
        {visiblePackages.map((item) => {
          const runtimeObservations = snapshot.run.expectedRuntimes.map((runtime) => ({
            runtime,
            result: item.runtimes[runtime],
            metadata: snapshot.runtimeMetadata[runtime],
          }));
          const jitObservation = runtimeObservations.find(({ runtime }) => runtime === "jit");
          const selectedRuntime = evidenceRuntimeByPackage[item.name] ?? "jit";
          const selectedRuntimeObservation = runtimeObservations.find(
            ({ runtime }) => runtime === selectedRuntime,
          ) ?? runtimeObservations[0];
          const observations = runtimeObservations.flatMap(({ result }) => (
            snapshot.run.expectedPlatforms.map((platform) => result?.platforms[platform])
          ));
          const commands = [...new Set(
            snapshot.run.expectedPlatforms.flatMap((platform) => {
              const command = selectedRuntimeObservation?.result?.platforms[platform]?.command;
              return command ? [command] : [];
            }),
          )];
          const explanations = [...new Set(
            observations.flatMap((observation) => observation?.explanation ? [observation.explanation] : []),
          )];
          const allNotTested = runtimeObservations.every(
            ({ result }) => !result || result.overallStatus === "not-tested",
          );

          return (
            <details className={`checklist-item ${item.overallStatus}`} key={item.name}>
              <summary>
                <span className="check-mark" aria-hidden="true">{statusMarks[item.overallStatus]}</span>
                <span className="package-title">
                  <b>{item.name}</b>
                  <span className="package-subline">
                    <small className="package-status">
                      {packageStatusLabel(item.runtimes)}
                    </small>
                    <small
                      className="package-meta"
                      title={`${item.downloads.toLocaleString("en-US")} downloads in 30 days`}
                    >
                      Rank {item.rank} · {compactNumber.format(item.downloads)} downloads / 30d
                    </small>
                  </span>
                </span>
                <span
                  className="runtime-checks"
                  aria-label="JIT platform statuses"
                >
                  {snapshot.run.expectedPlatforms.map((platform) => {
                    const status = jitObservation?.result?.platforms[platform]?.status ?? "not-tested";
                    return (
                      <span className={status} key={platform} title={statusLabels[status]}>
                        <b aria-hidden="true">{statusMarks[status]}</b>
                        {platform}
                        <span className="sr-only">
                          : {jitObservation?.result?.platforms[platform]?.label ?? statusLabels[status]}
                        </span>
                      </span>
                    );
                  })}
                </span>
                <span className="expand" aria-hidden="true">+</span>
              </summary>
              <div className="package-evidence" role="region" aria-label={`${item.name} run evidence`}>
                {allNotTested
                  ? (
                    <div className="not-tested-explanation">
                      <strong>Why this package was not tested</strong>
                      {(explanations.length ? explanations : ["No test result was captured for this package."])
                        .map((explanation) => <p key={explanation}>{explanation}</p>)}
                    </div>
                  )
                  : (
                    <>
                      {runtimeObservations.length > 1 && (
                        <div className="evidence-runtime-tabs" role="group" aria-label={`${item.name} evidence runtime`}>
                          {runtimeObservations.map(({ runtime, metadata }) => (
                            <button
                              type="button"
                              aria-pressed={selectedRuntimeObservation?.runtime === runtime}
                              key={runtime}
                              onClick={() => setEvidenceRuntimeByPackage((current) => ({
                                ...current,
                                [item.name]: runtime,
                              }))}
                            >
                              {metadata.label}
                            </button>
                          ))}
                        </div>
                      )}
                      {selectedRuntimeObservation && (
                        <section className="runtime-evidence" key={selectedRuntimeObservation.runtime}>
                          <h3 className="sr-only">{selectedRuntimeObservation.metadata.label}</h3>
                          {selectedRuntimeObservation.runtime === "free-threaded" && (
                            <p className="runtime-note">
                              Free-threaded CPython can run without the global interpreter lock.
                              This sanity check compares the same package suite with the GIL on and off.
                              It does not affect the package&apos;s JIT compatibility status.
                            </p>
                          )}
                          <div className="evidence-table-wrap">
                            <table className="evidence-table">
                              <caption className="sr-only">{item.name} {selectedRuntimeObservation.metadata.label} results by platform</caption>
                              <thead>
                                <tr>
                                  <th scope="col">Platform</th>
                                  <th scope="col">{selectedRuntimeObservation.metadata.baselineLabel}</th>
                                  <th scope="col">{selectedRuntimeObservation.metadata.targetLabel}</th>
                                  <th scope="col">Source</th>
                                </tr>
                              </thead>
                              <tbody>
                                {snapshot.run.expectedPlatforms.map((platform) => {
                                  const observation = selectedRuntimeObservation.result?.platforms[platform];
                                  if (!observation) return null;
                                  return (
                                    <Fragment key={platform}>
                                      <tr className={`evidence-result ${observation.status}`}>
                                        <th scope="row">
                                          <span>{platform}</span>
                                          <small>
                                            <i aria-hidden="true">{statusMarks[observation.status]}</i>
                                            {observation.label}
                                          </small>
                                        </th>
                                        <ConditionResult condition={observation.baseline} label={selectedRuntimeObservation.metadata.baselineLabel} />
                                        <ConditionResult condition={observation.target} label={selectedRuntimeObservation.metadata.targetLabel} />
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
                                      <FailureEvidence
                                        observation={observation}
                                        baselineLabel={selectedRuntimeObservation.metadata.baselineLabel}
                                        targetLabel={selectedRuntimeObservation.metadata.targetLabel}
                                      />
                                    </Fragment>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </section>
                      )}
                      {commands.length > 0 && (
                        <div className="evidence-commands">
                          <span>{commands.length === 1 ? "Command used" : "Commands used"}</span>
                          {commands.map((command) => (
                            <pre key={command}><code>{command}</code></pre>
                          ))}
                        </div>
                      )}
                    </>
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
