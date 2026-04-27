import { Routes, Route, Link, NavLink } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Wizard from "./pages/Wizard.jsx";
import NewProject from "./pages/NewProject.jsx";

export default function App() {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-[var(--color-line)] bg-white/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-semibold text-lg">
            <img
              src="/bd_gen_logo.svg"
              alt="Logo BdGEN"
              className="w-10 h-10 object-contain"
            />
            <span>BdGEN</span>
            <span className="text-sm font-normal text-[var(--color-mute)]">
              · générateur de bandes dessinées
            </span>
          </Link>
          <nav className="text-sm text-[var(--color-ink-soft)]">
            <NavLink to="/" end className="px-3 py-1.5 hover:text-[var(--color-ink)]">
              Accueil
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/new" element={<NewProject />} />
          <Route path="/projects/:name/*" element={<Wizard />} />
        </Routes>
      </main>

      <footer className="border-t border-[var(--color-line)] py-4 text-center text-xs text-[var(--color-mute)]">
        BdGEN · usage local
      </footer>
    </div>
  );
}
