import { useState } from "react";
import { login } from "../api/client";

interface Props {
  onUnlock: () => void;
}

/**
 * The one screen shown before the passcode is entered. The server holds the
 * passcode and sets an HttpOnly cookie on success, so this component never
 * stores anything itself -- it only asks.
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
    <form className="gate" onSubmit={handleSubmit}>
      <h1 className="gate-title">Enter passcode</h1>
      <p className="gate-note">This manual is private. You only need to do this once on this device.</p>
      <input
        className="gate-input"
        type="password"
        autoComplete="current-password"
        autoFocus
        aria-label="Passcode"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      {wrong && (
        <p className="gate-error" role="alert">
          That passcode didn't work. Try again.
        </p>
      )}
      <button className="gate-go" type="submit" disabled={!value || busy}>
        {busy ? "Checking…" : "Open"}
      </button>
    </form>
  );
}
