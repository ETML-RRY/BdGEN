import { useEffect } from "react";
import { useAppContext } from "../context/AppContext.jsx";

/**
 * Lets a step publish its declarative shell model (ribbon / sidebar / pager)
 * into the persistent desktop chrome. The slots are set while the step is
 * mounted and cleared on unmount so the shell never shows stale controls.
 *
 * Pass `null`/`undefined` for any slot the step doesn't use. The `deps` array
 * controls when the model is re-published (same contract as `useEffect`); list
 * every value the model closes over.
 *
 * @param {{ ribbon?: object, sidebar?: object, pager?: object }} model
 * @param {Array<any>} deps
 */
export function useRegisterShell({ ribbon = null, sidebar = null, pager = null } = {}, deps = []) {
  const { setRibbon, setSidebar, setPager } = useAppContext();

  useEffect(() => {
    setRibbon(ribbon);
    setSidebar(sidebar);
    setPager(pager);
    return () => {
      setRibbon(null);
      setSidebar(null);
      setPager(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export default useRegisterShell;
