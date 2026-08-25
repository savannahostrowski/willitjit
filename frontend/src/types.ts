export type Status =
  | "compatible"
  | "needs-triage"
  | "baseline-blocked"
  | "infrastructure-failure"
  | "not-tested";

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
  jit: Condition;
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
  platforms: Record<string, Observation>;
};

export type Snapshot = {
  run: {
    targetPackages: number;
    expectedPlatforms: string[];
    completedObservations: number;
    github?: { cpythonVersion?: string };
  };
  dataset: { source: string; releaseCutoff?: string };
  summary: {
    packages: Partial<Record<Status, number>>;
  };
  packages: PackageResult[];
};

export type HistoryPoint = {
  date: string;
  runId: string;
  pythonVersion: string | null;
  compatible: number;
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
  schemaVersion: 2;
  activeSeries: string | null;
  series: CompatibilitySeries[];
};

export type LegacyCompatibilityHistory = {
  schemaVersion: 1;
  pythonSeries: string;
  definition: string;
  points: Omit<HistoryPoint, "pythonVersion">[];
};
