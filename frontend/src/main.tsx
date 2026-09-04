import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CompatibilityHistory as HistoryChart } from "./CompatibilityHistory";
import { ResultsExplorer } from "./ResultsExplorer";
import { AboutPage, SiteFooter, SiteHeader, ToolsPage, type Theme } from "./SiteChrome";
import type {
  CompatibilityHistory,
  LegacySnapshot,
  PreviousCompatibilityHistory,
  ResultsIndex,
  Snapshot,
} from "./types";
import "./styles.css";

const DATA_ROOT = (
  import.meta.env.VITE_DATA_URL
  ?? "https://savannahostrowski.github.io/willitjit"
).replace(/\/$/, "");

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function normalizeHistory(
  history: CompatibilityHistory | PreviousCompatibilityHistory,
): CompatibilityHistory {
  if (history.schemaVersion === 4) return history;
  return { schemaVersion: 4, activeSeries: null, series: [] };
}

function normalizeSnapshot(snapshot: Snapshot | LegacySnapshot): Snapshot {
  if (snapshot.schemaVersion === 3) return snapshot;
  const expected = snapshot.run.expectedPlatforms.length * snapshot.run.targetPackages;
  return {
    ...snapshot,
    schemaVersion: 3,
    run: { ...snapshot.run, expectedRuntimes: ["jit"] },
    runtimeMetadata: {
      jit: { label: "JIT", baselineLabel: "JIT off", targetLabel: "JIT on" },
      "free-threaded": {
        label: "Free-threaded",
        baselineLabel: "GIL on",
        targetLabel: "GIL off",
      },
    },
    summary: {
      runtimes: {
        jit: {
          packages: snapshot.summary.packages,
          baselineEligible: snapshot.summary.baselineEligible ?? 0,
          completedObservations: snapshot.run.completedObservations ?? expected,
        },
      },
    },
    packages: snapshot.packages.map(({ baselineEligible, platforms, ...item }) => ({
      ...item,
      runtimes: {
        jit: {
          overallStatus: item.overallStatus,
          baselineEligible: baselineEligible ?? false,
          platforms: Object.fromEntries(
            Object.entries(platforms).map(([platform, observation]) => [
              platform,
              {
                ...observation,
                target: observation.jit,
              },
            ]),
          ),
        },
      },
    })),
  };
}

function pythonSeries(version: string | undefined) {
  return version?.match(/^(\d+\.\d+)/)?.[1] ?? "current";
}

function snapshotPath(path: string) {
  if (!/^[A-Za-z0-9._/-]+\.json$/.test(path) || path.includes("..") || path.startsWith("/")) {
    throw new Error("The results index contains an invalid snapshot path.");
  }
  return `${DATA_ROOT}/${path}`;
}

function Dashboard() {
  const [index, setIndex] = useState<ResultsIndex | null>(null);
  const [snapshots, setSnapshots] = useState<Record<string, Snapshot>>({});
  const [activeVersion, setActiveVersion] = useState<string | null>(null);
  const [history, setHistory] = useState<CompatibilityHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const historyRequest = fetchJson<CompatibilityHistory | PreviousCompatibilityHistory>(
      `${DATA_ROOT}/history.json`,
    );

    async function load() {
      let nextIndex: ResultsIndex;
      let nextSnapshots: Record<string, Snapshot>;
      try {
        nextIndex = await fetchJson<ResultsIndex>(`${DATA_ROOT}/index.json`);
        if (nextIndex.schemaVersion !== 1 || nextIndex.versions.length === 0) {
          throw new Error("The results index has an unsupported format.");
        }
        const entries = await Promise.all(nextIndex.versions.map(async (version) => [
          version.id,
          normalizeSnapshot(await fetchJson<Snapshot | LegacySnapshot>(snapshotPath(version.path))),
        ] as const));
        nextSnapshots = Object.fromEntries(entries);
      } catch {
        const snapshot = normalizeSnapshot(
          await fetchJson<Snapshot | LegacySnapshot>(`${DATA_ROOT}/results.json`),
        );
        const exactVersion = snapshot.run.github?.cpythonVersion ?? "Current";
        const id = pythonSeries(snapshot.run.github?.cpythonVersion);
        nextIndex = {
          schemaVersion: 1,
          defaultVersion: id,
          versions: [{ id, pythonVersion: exactVersion, path: "results.json" }],
        };
        nextSnapshots = { [id]: snapshot };
      }

      const nextHistory = normalizeHistory(await historyRequest);
      const requestedVersion = new URLSearchParams(window.location.search).get("python");
      const selectedVersion = requestedVersion && nextSnapshots[requestedVersion]
        ? requestedVersion
        : nextIndex.defaultVersion;
      if (!nextSnapshots[selectedVersion]) {
        throw new Error("The default Python version has no results snapshot.");
      }
      return { nextHistory, nextIndex, nextSnapshots, selectedVersion };
    }

    load()
      .then(({ nextHistory, nextIndex, nextSnapshots, selectedVersion }) => {
        if (cancelled) return;
        setIndex(nextIndex);
        setSnapshots(nextSnapshots);
        setActiveVersion(selectedVersion);
        setHistory(nextHistory);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(
          reason instanceof Error
            ? reason.message
            : "Results could not be loaded.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function selectVersion(version: string) {
    setActiveVersion(version);
    const url = new URL(window.location.href);
    url.searchParams.set("python", version);
    window.history.replaceState(null, "", url);
  }

  if (error) {
    return (
      <div className="load-state">
        <p className="eyebrow">Dashboard unavailable</p>
        <h1>Results could not be loaded.</h1>
        <p>{error}</p>
      </div>
    );
  }
  const snapshot = activeVersion ? snapshots[activeVersion] : null;
  if (!snapshot || !history || !index || !activeVersion) {
    return (
      <div className="load-state" aria-live="polite">
        <p className="eyebrow">Will It JIT?</p>
        <h1>Loading the latest compatibility snapshot…</h1>
      </div>
    );
  }
  return (
    <>
      <ResultsExplorer
        snapshot={snapshot}
        versions={index.versions}
        activeVersion={activeVersion}
        onVersionChange={selectVersion}
      />
      <HistoryChart history={history} />
    </>
  );
}

function initialTheme(): Theme {
  let theme: Theme;
  try {
    const stored = localStorage.getItem("willitjit-theme");
    if (stored === "light" || stored === "dark") {
      theme = stored;
    } else {
      theme = "light";
    }
  } catch {
    // Storage can be unavailable in privacy-focused browser contexts.
    theme = "light";
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  return theme;
}

function Root() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const page = path === "/about" ? "about" : path === "/tools" ? "tools" : "packages";

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try {
      localStorage.setItem("willitjit-theme", theme);
    } catch {
      // The selected theme still applies for this page view.
    }
  }, [theme]);

  useEffect(() => {
    document.title = page === "about"
      ? "About · Will It JIT?"
      : page === "tools"
        ? "Tools · Will It JIT?"
        : "Packages · Will It JIT?";
  }, [page]);

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <SiteHeader
        theme={theme}
        toggleTheme={() => setTheme((current) => current === "light" ? "dark" : "light")}
      />
      <main id="main-content" tabIndex={-1}>
        {page === "about" ? <AboutPage /> : page === "tools" ? <ToolsPage /> : <Dashboard />}
      </main>
      <SiteFooter />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
