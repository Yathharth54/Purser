import { useEffect, useState } from "react";
import { Chat } from "./components/Chat";
import { PageDrawer } from "./components/PageDrawer";
import { TocBrowser } from "./components/TocBrowser";
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
        <h1>Purser</h1>
        <nav className="tabs" aria-label="Sections">
          <button className={tab === "chat" ? "on" : ""} onClick={() => setTab("chat")}>
            Ask
          </button>
          <button
            className={tab === "manual" ? "on" : ""}
            onClick={() => {
              setSeenManual(true);
              setTab("manual");
            }}
          >
            Manual
          </button>
        </nav>
        <button
          type="button"
          className="theme-toggle"
          onClick={() => setTheme((t) => (t === "light" ? "cabin" : "light"))}
          aria-label={theme === "light" ? "Switch to cabin reading mode" : "Switch to day mode"}
        >
          {theme === "light" ? "Cabin" : "Day"}
        </button>
      </header>

      {/* Both panes stay mounted and are hidden with CSS rather than swapped.
          Chat owns the transcript and the thread id in local state, so
          unmounting it threw away her whole conversation the moment she
          tapped Manual to check something -- which is exactly what she does
          mid-procedure. Keeping it mounted also preserves scroll position.
          The manual pane is mounted lazily on first use, then kept. */}
      <main>
        <div className="pane" style={{ display: tab === "chat" ? "flex" : "none" }}>
          <Chat onOpenCitation={setCitation} />
        </div>
        {seenManual && (
          <div className="pane" style={{ display: tab === "manual" ? "flex" : "none" }}>
            <TocBrowser />
          </div>
        )}
      </main>

      <PageDrawer citation={citation} onClose={() => setCitation(null)} />
    </div>
  );
}
