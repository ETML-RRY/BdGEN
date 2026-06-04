import { useEffect, useState } from "react";
import { api } from "../api.js";

// One-shot check of /api/debug/enabled at mount. When the endpoint returns
// {enabled: true}, the dev-only trace surfaces (panel, route, nav link)
// become visible. In production BDGEN_DEBUG is unset so the gate stays closed.
//
// Returns { enabled: bool | null, ready: bool }. `enabled === null && ready`
// means the request finished but the answer was falsy (treat as disabled).
export function useDebugEnabled() {
  const [state, setState] = useState({ enabled: null, ready: false });

  useEffect(() => {
    let cancelled = false;
    api
      .debugEnabled()
      .then((res) => {
        if (cancelled) return;
        setState({ enabled: Boolean(res?.enabled), ready: true });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ enabled: false, ready: true });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
