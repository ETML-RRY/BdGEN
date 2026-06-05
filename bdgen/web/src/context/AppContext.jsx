import { createContext, useContext, useMemo, useState } from "react";

export const AppContext = createContext(null);

export function useAppContext() {
  return useContext(AppContext);
}

/**
 * Holds the state shared between the persistent desktop "shell" (title bar,
 * breadcrumb, ribbon, sidebar, status bar) and the routed step screens.
 *
 * Steps publish a declarative model into `ribbon` / `sidebar` / `pager` via
 * `useRegisterShell`; the shell renders it. `projectMeta` feeds the breadcrumb
 * and `runningJob` the status bar.
 */
export function AppProvider({ children }) {
  const [projectMeta, setProjectMeta] = useState(null);
  const [projectActions, setProjectActions] = useState(null);
  const [runningJob, setRunningJob] = useState(null);
  const [ribbon, setRibbon] = useState(null);
  const [sidebar, setSidebar] = useState(null);
  const [pager, setPager] = useState(null);

  const value = useMemo(
    () => ({
      projectMeta,
      setProjectMeta,
      projectActions,
      setProjectActions,
      runningJob,
      setRunningJob,
      ribbon,
      setRibbon,
      sidebar,
      setSidebar,
      pager,
      setPager,
    }),
    [projectMeta, projectActions, runningJob, ribbon, sidebar, pager],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
