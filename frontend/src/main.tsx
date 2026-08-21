import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CompatibilityHistory as HistoryChart } from "./CompatibilityHistory";
import { ResultsExplorer } from "./ResultsExplorer";
import { AboutPage, SiteFooter, SiteHeader, type Theme } from "./SiteChrome";
import type { CompatibilityHistory, Snapshot } from "./types";
import "./styles.css";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function Dashboard() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [history, setHistory] = useState<CompatibilityHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetchJson<Snapshot>("/data/results.json"),
      fetchJson<CompatibilityHistory>("/data/history.json"),
    ])
      .then(([nextSnapshot, nextHistory]) => {
        setSnapshot(nextSnapshot);
        setHistory(nextHistory);
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
      theme = "dark";
    }
  } catch {
    // Storage can be unavailable in privacy-focused browser contexts.
    theme = "dark";
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  return theme;
}

function Root() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const aboutPage = window.location.pathname.replace(/\/$/, "") === "/about";

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
    document.title = aboutPage ? "About · Will It JIT?" : "Will It JIT?";
  }, [aboutPage]);

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <SiteHeader
        theme={theme}
        toggleTheme={() => setTheme((current) => current === "light" ? "dark" : "light")}
      />
      <main id="main-content">
        {aboutPage ? <AboutPage /> : <Dashboard />}
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
