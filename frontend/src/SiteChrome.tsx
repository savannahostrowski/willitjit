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
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const currentPage = path === "/about" ? "about" : path === "/tools" ? "tools" : "packages";
  const themeLabel = theme === "dark" ? "Use light theme" : "Use dark theme";
  return (
    <header className="site-header">
      <a className="site-logo" href="/">Will It JIT?</a>
      <nav aria-label="Primary navigation">
        <a href="/packages" aria-current={currentPage === "packages" ? "page" : undefined}>Packages</a>
        <a href="/tools" aria-current={currentPage === "tools" ? "page" : undefined}>Tools</a>
        <a href="/about" aria-current={currentPage === "about" ? "page" : undefined}>About</a>
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
      </header>

      <div className="about-body">
        <section>
          <h2>Packages</h2>
          <p>
            Each project gets two fresh checkouts and virtual environments. We run
            its test suite with <code>PYTHON_JIT=0</code> first. If that passes, we
            run the same release, setup steps, and test command with
            <code>PYTHON_JIT=1</code>. If the first run fails, we stop there. The
            package is marked as a baseline failure and is not counted against the
            JIT compatibility rate.
          </p>
          <p>
            Python projects all install and test themselves differently. The
            registry has one small TOML file per package with its pinned release,
            install steps, test command, working directory, timeout, and any extra
            fixtures it needs. The adapter does not replace the project&apos;s tests.
            It tells the runner how to run them, and both sides of the comparison
            use the same file. We also use it for a separate free-threaded check
            with the GIL on and off. That check does not affect the JIT result.
          </p>
        </section>
        <section>
          <h2>Tools</h2>
          <p>
            We are also working on checks for debuggers, profilers, and other tools
            that need to understand running Python code. Those checks will have
            their own results and will stay separate from the package compatibility
            rate.
          </p>
        </section>
        <section>
          <h2>Data</h2>
          <p>
            The registry follows the top 100 entries in the{" "}
            <a href="https://github.com/hugovk/top-pypi-packages" target="_blank" rel="noreferrer">
              Top PyPI Packages list
            </a>.
            Releases are pinned while a survey runs across Linux, macOS, and
            Windows. Only GitHub-hosted sources are tested for now. Packages hosted
            elsewhere stay on the list as not tested.
          </p>
          <p>
            Results include the source revision, command used, test summary, run
            time, failure output, and a link to the GitHub Actions run. The runner
            and package adapters are also available on{" "}
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>.
          </p>
        </section>
      </div>
    </article>
  );
}

export function ToolsPage() {
  return (
    <article className="about-page">
      <header>
        <p className="eyebrow">Tools</p>
        <h1>Tool compatibility</h1>
      </header>
      <div className="about-body">
        <section>
          <h2>In progress</h2>
          <p>
            This page will track whether debuggers, profilers, and related Python
            tools work correctly with CPython&apos;s JIT. Tool checks need different
            test cases from package suites, so their results will live here instead
            of being mixed into package compatibility.
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
        <a href="/packages">Packages</a>
        <a href="/tools">Tools</a>
        <a href="/about">About</a>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
      </nav>
    </footer>
  );
}
