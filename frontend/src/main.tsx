import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CompatibilityHistory as HistoryChart } from "./CompatibilityHistory";
import { ResultsExplorer } from "./ResultsExplorer";
import { AboutPage, SiteFooter, SiteHeader, ToolsPage, type Theme } from "./SiteChrome";
import type {
  CompatibilityHistory,
  LegacySnapshot,
  PreviousCompatibilityHistory,
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
  if (history.schemaVersion === 3) return history;
  return { schemaVersion: 3, activeSeries: null, series: [] };
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

function Dashboard() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [history, setHistory] = useState<CompatibilityHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetchJson<Snapshot | LegacySnapshot>(`${DATA_ROOT}/results.json`),
      fetchJson<CompatibilityHistory | PreviousCompatibilityHistory>(`${DATA_ROOT}/history.json`),
    ])
      .then(([nextSnapshot, nextHistory]) => {
        setSnapshot(normalizeSnapshot(nextSnapshot));
        setHistory(normalizeHistory(nextHistory));
      })
      .catch((reason: unknown) => {
        setError(
          reason instanceof Error
            ? reason.message
            : "Results could not be loaded.",
        );
      });
  }, []);

  if (error) {
    return (
      <div className="load-state">
        <p className="eyebrow">Dashboard unavailable</p>
        <h1>Results could not be loaded.</h1>
        <p>{error}</p>
      </div>
    );
  }
  if (!snapshot || !history) {
    return (
      <div className="load-state" aria-live="polite">
        <p className="eyebrow">Will It JIT?</p>
        <h1>Loading the latest compatibility snapshot…</h1>
      </div>
    );
  }
  return (
    <>
      <ResultsExplorer snapshot={snapshot} />
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
