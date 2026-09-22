import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import "./styles/tokens.css";

// Task 17 scaffold only: no chat UI, no routes. Task 18 replaces this with
// the real app tree under src/components and src/routes; this placeholder
// exists so the PWA has something to render and the font/color tokens and
// the API client can be exercised end-to-end.
function App(): React.JSX.Element {
  return (
    <main style={{ padding: "1rem" }}>
      <h1 style={{ fontFamily: "var(--font-ui)" }}>Purser</h1>
      <p style={{ color: "var(--dim)" }}>PWA scaffold -- UI lands in Task 18.</p>
    </main>
  );
}

const queryClient = new QueryClient();

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root element not found");
}

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
