import { useState } from "react";
import { login } from "../api/client";

interface Props {
  onUnlock: () => void;
}

/**
 * The one screen shown before the passcode is entered, set as the cover of
 * the manual it opens: its title in the running head, the mark, and the
 * one field. The server holds the passcode and sets an HttpOnly cookie on
 * success, so this component never stores anything itself -- it only asks.
 */
export function PasscodeGate({ onUnlock }: Props) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [wrong, setWrong] = useState(false);

  async function handleSubmit(event: { preventDefault(): void }) {
    event.preventDefault();
    if (!value || busy) return;
    setBusy(true);
    setWrong(false);
    try {
      if (await login(value)) onUnlock();
      else setWrong(true);
    } catch {
      setWrong(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate-page">
      <div className="gate-cover">
        <p className="gate-kicker">Safety and Emergency Procedures Manual</p>
        <span className="gate-rule" aria-hidden="true" />
        <img className="gate-mark" src="/icons/icon-180.png" alt="" width={84} height={84} />
        <h1 className="gate-title">Purser</h1>
        <p className="gate-sub">the manual, answered</p>
      </div>

      <form className="gate" onSubmit={handleSubmit} aria-label="Enter passcode">
        <label className="gate-label" htmlFor="gate-input">
          Crew access
        </label>
        <div className={wrong ? "gate-field gate-field-wrong" : "gate-field"}>
          <input
            id="gate-input"
            className="gate-input"
            type="password"
            autoComplete="current-password"
            autoFocus
            placeholder="Passcode"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-invalid={wrong || undefined}
            aria-describedby={wrong ? "gate-error" : "gate-note"}
          />
          <button
            className="gate-go"
            type="submit"
            disabled={!value || busy}
            aria-label={busy ? "Checking" : "Open"}
            aria-busy={busy || undefined}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 12h14" />
              <path d="m13 6 6 6-6 6" />
            </svg>
          </button>
        </div>
        {wrong ? (
          <p className="gate-error" id="gate-error" role="alert">
            That passcode didn't work. Try again.
          </p>
        ) : (
          <p className="gate-note" id="gate-note">
            {busy ? "Checking…" : "Private to the crew. You only need this once on this device."}
          </p>
        )}
      </form>

      <p className="gate-foot">Airbus A320 · A321 · cited to the page</p>
    </div>
  );
}
