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
  name: string;
  repository: string;
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
  dataset: { source: string };
  summary: {
    packages: Partial<Record<Status, number>>;
  };
  packages: PackageResult[];
};

export type HistoryPoint = {
  date: string;
  runId: string;
  compatible: number;
  total: number;
};

export type CompatibilityHistory = {
  pythonSeries: string;
  definition: string;
  points: HistoryPoint[];
};
