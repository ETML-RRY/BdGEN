import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { AppProvider } from "./context/AppContext.jsx";
import { loadInitialLanguage } from "./i18n/index.js";
import "./index.css";

// Block the first React render until i18n is ready so users never see a
// flash of untranslated (French) strings. The static "Loading…" text is
// the only thing visible during this short window.
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <div className="min-h-full flex items-center justify-center text-sm text-[var(--color-mute)]">
    Loading…
  </div>,
);

loadInitialLanguage().then(() => {
  root.render(
    <React.StrictMode>
      <BrowserRouter>
        <AppProvider>
          <App />
        </AppProvider>
      </BrowserRouter>
    </React.StrictMode>,
  );
});
