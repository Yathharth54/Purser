import { useEffect, useRef, useState } from "react";
import { fetchSession, LOCKED_EVENT } from "./api/client";
import { Chat } from "./components/Chat";
import { PasscodeGate } from "./components/PasscodeGate";
import { PageDrawer } from "./components/PageDrawer";
import { TocBrowser } from "./components/TocBrowser";
import { Wordmark } from "./components/Wordmark";
import type { Citation } from "./api/types";
import "./styles.css";

type Theme = "day" | "cabin";

function loadTheme(): Theme {
  try {
    const saved = window.localStorage.getItem("purser-theme");
    // "light" was this value's name before the CSS's own "day"/"cabin" naming
    // was made the source of truth -- migrate an existing install rather than
    // silently falling back to the default below.
    if (saved === "light") return "day";
    if (saved === "day" || saved === "cabin") return saved;
  } catch {
    // localStorage unavailable (private mode, etc.) -- fall through to default.
  }
  // No explicit choice yet. Day is the primary design, but she opens this in a
  // darkened cabin with her phone already in dark mode -- honour that on first run
  // rather than flashing a white screen at her mid-duty. An explicit toggle always
  // wins over this, because it is stored above.
  try {
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "cabin";
  } catch {
    // matchMedia unavailable -- fall through.
  }
  return "day";
}

export default function App() {
  const [tab, setTab] = useState<"chat" | "manual">("chat");
  const [seenManual, setSeenManual] = useState(false);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [chatsOpen, setChatsOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(loadTheme);
  // "checking" until the server says whether this device holds a session.
  const [access, setAccess] = useState<"checking" | "locked" | "open">("checking");
  const chatTabRef = useRef<HTMLButtonElement>(null);
  const manualTabRef = useRef<HTMLButtonElement>(null);

  // Chats belong to Ask: opening them from the Manual tab goes back there,
  // so the chat she picks is on screen when the panel closes.
  function openChats() {
    selectTab("chat");
    setChatsOpen(true);
  }

  function selectTab(next: "chat" | "manual") {
    if (next === "manual") setSeenManual(true);
    setTab(next);
  }

  // ARIA Tabs pattern: the tablist is a single Tab stop (roving tabindex --
  // only the selected tab is tabbable) and ArrowLeft/ArrowRight/Home/End
  // move both the selection and focus between the two tabs. Without the
  // focus move, a screen-reader user who reaches for the arrow keys after
  // landing on "tab, 1 of 2" gets nothing.
  function handleSegKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    let next: "chat" | "manual" | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      next = tab === "chat" ? "manual" : "chat";
    } else if (event.key === "Home") {
      next = "chat";
    } else if (event.key === "End") {
      next = "manual";
    }
    if (!next) return;
    event.preventDefault();
    selectTab(next);
    (next === "chat" ? chatTabRef : manualTabRef).current?.focus();
  }

  useEffect(() => {
    void fetchSession()
      .then((s) => setAccess(s.authenticated ? "open" : "locked"))
      // Can't reach the server: show the app and let its own requests report
      // the problem, rather than a passcode screen that could never succeed.
      .catch(() => setAccess("open"));
    const lock = () => setAccess("locked");
    window.addEventListener(LOCKED_EVENT, lock);
    return () => window.removeEventListener(LOCKED_EVENT, lock);
  }, []);

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
          {access === "open" ? (
            <button
              type="button"
              className="head-btn"
              onClick={openChats}
              aria-label="Your chats"
              aria-haspopup="dialog"
              aria-expanded={chatsOpen}
            >
              <span className="head-btn-chip" aria-hidden="true">
                <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
                  <path d="M9.5 4.5v15" />
                </svg>
              </span>
            </button>
          ) : (
            // Holds the left slot so the wordmark stays centred behind the lock.
            <span className="head-btn" aria-hidden="true" />
          )}
          <Wordmark />
          <button
            type="button"
            className="head-btn"
            onClick={() => setTheme((t) => (t === "day" ? "cabin" : "day"))}
            aria-label={theme === "day" ? "Switch to cabin reading mode" : "Switch to day mode"}
          >
            <span className="head-btn-chip" aria-hidden="true">
              {theme === "day" ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20.5 13.5A8.5 8.5 0 1 1 10.5 3.5a6.6 6.6 0 0 0 10 10Z" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                </svg>
              )}
            </span>
          </button>
        </div>
        {access === "open" && (
          <div
            className={tab === "manual" ? "seg seg-manual" : "seg"}
            role="tablist"
            aria-label="Sections"
          >
            <button
              type="button"
              role="tab"
              id="tab-chat"
              ref={chatTabRef}
              tabIndex={tab === "chat" ? 0 : -1}
              aria-selected={tab === "chat"}
              aria-controls="panel-chat"
              className={tab === "chat" ? "on" : undefined}
              onClick={() => selectTab("chat")}
              onKeyDown={handleSegKeyDown}
            >
              Ask
            </button>
            <button
              type="button"
              role="tab"
              id="tab-manual"
              ref={manualTabRef}
              tabIndex={tab === "manual" ? 0 : -1}
              aria-selected={tab === "manual"}
              aria-controls="panel-manual"
              className={tab === "manual" ? "on" : undefined}
              onClick={() => selectTab("manual")}
              onKeyDown={handleSegKeyDown}
            >
              Manual
            </button>
          </div>
        )}
      </header>

      {access === "checking" && (
        <main>
          {/* The server may be waking up (a cold start takes a few seconds). */}
          <p className="opening" role="status">
            Opening the manual…
          </p>
        </main>
      )}

      {access === "locked" && (
        <main>
          <PasscodeGate onUnlock={() => setAccess("open")} />
        </main>
      )}

      {access === "open" && (
        <>
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
              <Chat
                onOpenCitation={setCitation}
                chatsOpen={chatsOpen}
                onCloseChats={() => setChatsOpen(false)}
              />
            </div>
            <div
              className="pane"
              id="panel-manual"
              role="tabpanel"
              aria-labelledby="tab-manual"
              style={{ display: tab === "manual" ? "flex" : "none" }}
            >
              {seenManual && <TocBrowser />}
            </div>
          </main>

          <PageDrawer citation={citation} onClose={() => setCitation(null)} />
        </>
      )}
    </div>
  );
}
