export type Theme = "light" | "dark";

const GITHUB_URL = "https://github.com/savannahostrowski/willitjit";

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function ThemeIcon({ theme }: { theme: Theme }) {
  return theme === "dark" ? (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3 6.5 6.5 0 0 0 21 12.8Z" />
    </svg>
  );
}

export function SiteHeader({ theme, toggleTheme }: { theme: Theme; toggleTheme: () => void }) {
  const aboutPage = window.location.pathname.replace(/\/$/, "") === "/about";
  const themeLabel = theme === "dark" ? "Use light theme" : "Use dark theme";
  return (
    <header className="site-header">
      <a className="site-logo" href="/">Will It JIT?</a>
      <nav aria-label="Primary navigation">
        <a href="/" aria-current={aboutPage ? undefined : "page"}>Results</a>
        <a href="/about" aria-current={aboutPage ? "page" : undefined}>About</a>
        <a
          className="github-link"
          href={GITHUB_URL}
          target="_blank"
          rel="noreferrer"
          aria-label="GitHub"
        >
          <GitHubIcon />
          <span>GitHub</span>
        </a>
        <button
          className="theme-toggle"
          type="button"
          onClick={toggleTheme}
          aria-label={themeLabel}
          title={themeLabel}
        >
          <ThemeIcon theme={theme} />
        </button>
      </nav>
    </header>
  );
}

export function AboutPage() {
  return (
    <article className="about-page">
      <header>
        <p className="eyebrow">About</p>
        <h1>About Will It JIT?</h1>
        <p>
          Will It JIT? checks whether popular Python packages behave differently
          when CPython&apos;s experimental JIT is enabled.
        </p>
      </header>

      <div className="about-sections">
        <section>
          <h2>How it works</h2>
          <p>
            For each package, the runner creates two clean checkouts and virtual
            environments. It runs the package&apos;s own test suite once with
            <code>PYTHON_JIT=0</code> and once with <code>PYTHON_JIT=1</code>.
          </p>
        </section>
        <section>
          <h2>Results</h2>
          <p>
            Compatible means both runs passed on every reported platform. If the
            JIT-off run fails, the JIT-on run is skipped. If only the JIT-on run
            fails, the result is marked for investigation. It is not declared a CPython bug.
          </p>
        </section>
        <section>
          <h2>Packages</h2>
          <p>
            The package list comes from the{" "}
            <a href="https://github.com/hugovk/top-pypi-packages" target="_blank" rel="noreferrer">
              Top PyPI Packages list
            </a>.
            The registry currently includes the first 100 packages on that list whose
            source is hosted on GitHub. Other source hosts are out of scope for now.
            The weekly survey runs all 100.
          </p>
        </section>
        <section>
          <h2>Code</h2>
          <p>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">View the project on GitHub</a>.
          </p>
        </section>
      </div>
    </article>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p>Will It JIT? · CPython JIT compatibility</p>
      <nav aria-label="Footer navigation">
        <a href="/about">About</a>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
      </nav>
    </footer>
  );
}
