import { useEffect, useState } from "react";
import { Chat } from "./components/Chat";
import { PageDrawer } from "./components/PageDrawer";
import { TocBrowser } from "./components/TocBrowser";
import { Wordmark } from "./components/Wordmark";
import type { Citation } from "./api/types";
import "./styles.css";

type Theme = "light" | "cabin";

function loadTheme(): Theme {
  try {
    const saved = window.localStorage.getItem("purser-theme");
    if (saved === "light" || saved === "cabin") return saved;
  } catch {
    // localStorage unavailable (private mode, etc.) -- fall through to default.
  }
  // No explicit choice yet. Light is the primary design, but she opens this in a
  // darkened cabin with her phone already in dark mode -- honour that on first run
  // rather than flashing a white screen at her mid-duty. An explicit toggle always
  // wins over this, because it is stored above.
  try {
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "cabin";
  } catch {
    // matchMedia unavailable -- fall through.
  }
  return "light";
}

export default function App() {
  const [tab, setTab] = useState<"chat" | "manual">("chat");
  const [seenManual, setSeenManual] = useState(false);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [theme, setTheme] = useState<Theme>(loadTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("purser-theme", theme);
    } catch {
      // Ignore -- theme just won't persist across reloads.
    }
  }, [theme]);

  return (
    <div className="app">
      <header className="app-head">
        <div className="head-row">
          <Wordmark />
          <span className="head-spacer" aria-hidden="true" />
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme((t) => (t === "light" ? "cabin" : "light"))}
            aria-label={theme === "light" ? "Switch to cabin reading mode" : "Switch to day mode"}
          >
            <span className="theme-toggle-icon" aria-hidden="true">
              {theme === "light" ? "☾" : "☀"}
            </span>
          </button>
        </div>
        <div
          className={tab === "manual" ? "seg seg-manual" : "seg"}
          role="tablist"
          aria-label="Sections"
        >
          <button
            type="button"
            role="tab"
            id="tab-chat"
            aria-selected={tab === "chat"}
            aria-controls="panel-chat"
            className={tab === "chat" ? "on" : undefined}
            onClick={() => setTab("chat")}
          >
            Ask
          </button>
          <button
            type="button"
            role="tab"
            id="tab-manual"
            aria-selected={tab === "manual"}
            aria-controls="panel-manual"
            className={tab === "manual" ? "on" : undefined}
            onClick={() => {
              setSeenManual(true);
              setTab("manual");
            }}
          >
            Manual
          </button>
        </div>
      </header>

      {/* Both panes stay mounted and are hidden with CSS rather than swapped.
          Chat owns the transcript and the thread id in local state, so
          unmounting it threw away her whole conversation the moment she
          tapped Manual to check something -- which is exactly what she does
          mid-procedure. Keeping it mounted also preserves scroll position.
          The manual pane is mounted lazily on first use, then kept. */}
      <main>
        <div
          className="pane"
          id="panel-chat"
          role="tabpanel"
          aria-labelledby="tab-chat"
          style={{ display: tab === "chat" ? "flex" : "none" }}
        >
          <Chat onOpenCitation={setCitation} />
        </div>
        {seenManual && (
          <div
            className="pane"
            id="panel-manual"
            role="tabpanel"
            aria-labelledby="tab-manual"
            style={{ display: tab === "manual" ? "flex" : "none" }}
          >
            <TocBrowser />
          </div>
        )}
      </main>

      <PageDrawer citation={citation} onClose={() => setCitation(null)} />
    </div>
  );
}
