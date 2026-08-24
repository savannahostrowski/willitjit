import { Fragment } from "react";

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
  "not-tested": "Not completed",
};

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
  const compatible = snapshot.summary.packages.compatible ?? 0;
  const pending = snapshot.run.completedObservations === 0;
  const cpythonVersion = snapshot.run.github?.cpythonVersion ?? "3.14.6";
  const cpythonLabel = cpythonVersion.replace(".0rc", " RC").toUpperCase();

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
            : `${compatible} of ${snapshot.run.targetPackages} compatible`}
        >
          <span>{pending ? "Target" : "Latest survey"}</span>
          <strong>
            {pending ? cpythonLabel : compatible}
            {!pending && <small> of {snapshot.run.targetPackages}</small>}
          </strong>
          <p>{pending ? "survey pending" : "packages compatible"}</p>
        </div>
      </div>

      <div className="checklist" aria-label="Package compatibility results">
        {snapshot.packages.map((item) => {
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
                <small>{statusLabels[item.overallStatus]}</small>
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
      </div>
    </section>
  );
}
