import type { Condition, Observation, Snapshot, Status } from "./types";

const statusMarks: Record<Status, string> = {
  compatible: "✓",
  "needs-triage": "!",
  "baseline-blocked": "−",
  "infrastructure-failure": "×",
  "not-tested": "·",
};

const statusLabels: Record<Status, string> = {
  compatible: "Compatible everywhere tested",
  "needs-triage": "Needs JIT triage",
  "baseline-blocked": "Blocked by baseline",
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

function ConditionSummary({ condition }: { condition: NonNullable<Condition> }) {
  return (
    <small>
      {condition.suiteSummary}
      <span className="runner-time">Runner time: {elapsedLabel(condition.elapsedSeconds)}</span>
    </small>
  );
}

function PlatformEvidence({
  name,
  observation,
  repository,
}: {
  name: string;
  observation: Observation;
  repository: string;
}) {
  return (
    <article className={`platform-card ${observation.status}`}>
      <header>
        <span>{name}</span>
        <b><i>{statusMarks[observation.status]}</i>{observation.label}</b>
      </header>
      {observation.status !== "compatible" && <p>{observation.explanation}</p>}
      <dl>
        <div>
          <dt>JIT off</dt>
          <dd>{conditionLabel(observation.baseline)}</dd>
          {observation.baseline
            ? <ConditionSummary condition={observation.baseline} />
            : <small>No result captured.</small>}
          {observation.baseline?.failureExcerpt && <code>{observation.baseline.failureExcerpt}</code>}
        </div>
        <div>
          <dt>JIT on</dt>
          <dd>{conditionLabel(observation.jit)}</dd>
          {observation.jit
            ? <ConditionSummary condition={observation.jit} />
            : <small>No result captured.</small>}
          {observation.jit?.failureExcerpt && <code>{observation.jit.failureExcerpt}</code>}
        </div>
      </dl>
      <footer>
        {observation.command && <code>{observation.command}</code>}
        {observation.revision && (
          <a href={`${repository}/commit/${observation.revision}`} target="_blank" rel="noreferrer">
            revision {observation.revision.slice(0, 9)} ↗
          </a>
        )}
      </footer>
    </article>
  );
}

export function ResultsExplorer({ snapshot }: { snapshot: Snapshot }) {
  const compatible = snapshot.summary.packages.compatible ?? 0;
  const pending = snapshot.run.completedObservations === 0;
  const cpythonVersion = snapshot.run.github?.cpythonVersion ?? "3.15.0rc1";
  const cpythonLabel = cpythonVersion.replace(".0rc", " RC").toUpperCase();

  return (
    <section className="results-section" id="results">
      <div className="checklist-heading">
        <div>
          <h1>Will It JIT?</h1>
          <p>
            Packages are ranked by the <a href={snapshot.dataset.source}>Top PyPI Packages</a> dataset.
            Compatible means every reported platform passed the package&apos;s upstream suite with the JIT both off and on.
          </p>
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
        {snapshot.packages.map((item) => (
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
              <div className="platform-grid">
                {snapshot.run.expectedPlatforms.map((platform) => (
                  <PlatformEvidence
                    key={platform}
                    name={platform}
                    observation={item.platforms[platform]}
                    repository={item.repository}
                  />
                ))}
              </div>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
