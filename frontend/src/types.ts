export type Status =
  | "compatible"
  | "needs-triage"
  | "baseline-blocked"
  | "infrastructure-failure"
  | "not-tested";

export type Runtime = "jit" | "free-threaded";

export type Condition = {
  returnCode: number | null;
  timedOut: boolean;
  elapsedSeconds: number;
  suiteSummary: string;
  failureExcerpt: string | null;
} | null;

export type Observation = {
  status: Status;
  label: string;
  explanation: string;
  revision: string | null;
  command: string | null;
  baseline: Condition;
  target: Condition;
};

export type RuntimeResult = {
  overallStatus: Status;
  baselineEligible: boolean;
  platforms: Record<string, Observation>;
};

export type PackageResult = {
  rank: number;
  name: string;
  downloads: number;
  repository: string;
  releaseVersion?: string;
  releaseDate?: string;
  sourceRef?: string;
  overallStatus: Status;
  runtimes: Partial<Record<Runtime, RuntimeResult>>;
};

export type RuntimeSummary = {
  packages: Partial<Record<Status, number>>;
  baselineEligible: number;
  completedObservations: number;
};

export type Snapshot = {
  schemaVersion: 3;
  run: {
    targetPackages: number;
    expectedPlatforms: string[];
    expectedRuntimes: Runtime[];
    completedObservations: number;
    github?: {
      cpythonVersion?: string;
      repository?: string;
      runId?: string;
    };
  };
  dataset: { source: string; releaseCutoff?: string };
  runtimeMetadata: Record<Runtime, {
    label: string;
    baselineLabel: string;
    targetLabel: string;
  }>;
  summary: { runtimes: Partial<Record<Runtime, RuntimeSummary>> };
  packages: PackageResult[];
};

export type LegacySnapshot = {
  schemaVersion?: 2;
  run: Omit<Snapshot["run"], "expectedRuntimes">;
  dataset: Snapshot["dataset"];
  summary: {
    packages: Partial<Record<Status, number>>;
    baselineEligible?: number;
  };
  packages: Array<Omit<PackageResult, "runtimes"> & {
    baselineEligible?: boolean;
    platforms: Record<string, Omit<Observation, "target"> & { jit: Condition }>;
  }>;
};

export type HistoryPoint = {
  date: string;
  runId: string;
  pythonVersion: string | null;
  compatible: number;
  baselineEligible: number;
  total: number;
};

export type CompatibilitySeries = {
  id: string;
  pythonSeries: string;
  packageCount: number;
  datasetUpdated: string | null;
  points: HistoryPoint[];
};

export type CompatibilityHistory = {
  schemaVersion: 3;
  activeSeries: string | null;
  series: CompatibilitySeries[];
};

export type PreviousCompatibilityHistory =
  { schemaVersion: 1 | 2 };
