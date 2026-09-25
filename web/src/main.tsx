import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Analytics } from "@vercel/analytics/react";

import "./styles/tokens.css";
import App from "./App";

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
    {/* Vercel Web Analytics: page views only -- no cookies, no question text.
        Serves nothing unless Analytics is enabled on the Vercel project. */}
    <Analytics />
  </StrictMode>,
);
