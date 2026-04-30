// Tiny API client. All endpoints are same-origin in production (FastAPI serves
// the built frontend) and proxied in dev (vite.config.js).

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let body;
    try {
      body = await res.json();
    } catch {
      body = { detail: await res.text() };
    }
    const err = new Error(body.detail || res.statusText);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request("/api/health"),

  listProjects: () => request("/api/projects"),
  getProject: (name) => request(`/api/projects/${encodeURIComponent(name)}`),
  getProjectStatistics: (name) =>
    request(`/api/projects/${encodeURIComponent(name)}/statistics`),
  createProject: (config) =>
    request("/api/projects", { method: "POST", body: JSON.stringify(config) }),
  updateProject: (name, config) =>
    request(`/api/projects/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  deleteProject: (name) =>
    request(`/api/projects/${encodeURIComponent(name)}`, { method: "DELETE" }),
  duplicateProject: (
    name,
    {
      newProject = null,
      includeReferences = false,
      includePhotos = true,
      includeStyleReference = true,
    } = {}
  ) =>
    request(`/api/projects/${encodeURIComponent(name)}/duplicate`, {
      method: "POST",
      body: JSON.stringify({
        new_project: newProject,
        include_references: includeReferences,
        include_photos: includePhotos,
        include_style_reference: includeStyleReference,
      }),
    }),
  restyleProject: (name, style) =>
    request(`/api/projects/${encodeURIComponent(name)}/restyle`, {
      method: "POST",
      body: JSON.stringify({ style }),
    }),
  feedback: (name) => request(`/api/projects/${encodeURIComponent(name)}/feedback`),

  exportUrl: (name) => `/api/projects/${encodeURIComponent(name)}/export`,
  importProject: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/projects/import", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  listExportableReferences: (name) =>
    request(`/api/projects/${encodeURIComponent(name)}/references/exportable`),
  exportReferencesBundle: async (name, picks) => {
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/references/export`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(picks),
      }
    );
    if (!res.ok) {
      let body;
      try { body = await res.json(); } catch { body = { detail: await res.text() }; }
      throw new Error(body.detail || res.statusText);
    }
    return res.blob();
  },
  importReferencesBundle: async (name, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/references/import`,
      { method: "POST", body: fd }
    );
    if (!res.ok) {
      let body;
      try { body = await res.json(); } catch { body = { detail: await res.text() }; }
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  },

  currentJob: () => request("/api/jobs/current"),
  interruptJob: () =>
    request("/api/jobs/current/interrupt", { method: "POST" }),
  clearJob: () => request("/api/jobs/current/clear", { method: "POST" }),

  startStep: (name, step, payload = {}) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/steps/${step}/start`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  regenerateAll: (name, step, qualityOverride) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/steps/${step}/start`,
      {
        method: "POST",
        body: JSON.stringify({
          force_all: true,
          quality_override: qualityOverride || undefined,
        }),
      }
    ),
  // Convenience helper: launches a force-regeneration of a single target at
  // high quality, used by the per-item "Améliorer la qualité" buttons.
  upgradeQuality: (name, step, targetIds) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/steps/${step}/start`,
      {
        method: "POST",
        body: JSON.stringify({
          force_ids: targetIds,
          quality_override: "high",
        }),
      }
    ),

  refineCharacter: (name, id, feedback) =>
    request(`/api/projects/${encodeURIComponent(name)}/refine/character/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  refineLocation: (name, id, feedback) =>
    request(`/api/projects/${encodeURIComponent(name)}/refine/location/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  refineObject: (name, id, feedback) =>
    request(`/api/projects/${encodeURIComponent(name)}/refine/object/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  refinePage: (name, n, feedback, cascade = false) =>
    request(`/api/projects/${encodeURIComponent(name)}/refine/page/${n}`, {
      method: "POST",
      body: JSON.stringify({ feedback, cascade }),
    }),
  previewDeleteCharacter: (name, id) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(id)}/delete-preview`
    ),
  previewDeleteLocation: (name, id) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(id)}/delete-preview`
    ),
  previewDeleteObject: (name, id) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(id)}/delete-preview`
    ),
  deleteCharacter: (name, id, autoRegenerate = true) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(id)}?auto_regenerate=${autoRegenerate}`,
      { method: "DELETE" }
    ),
  deleteLocation: (name, id, autoRegenerate = true) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(id)}?auto_regenerate=${autoRegenerate}`,
      { method: "DELETE" }
    ),
  deleteObject: (name, id, autoRegenerate = true) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(id)}?auto_regenerate=${autoRegenerate}`,
      { method: "DELETE" }
    ),

  refineCover: (name, feedback) =>
    request(`/api/projects/${encodeURIComponent(name)}/refine/cover`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  refineBackCover: (name, feedback) =>
    request(`/api/projects/${encodeURIComponent(name)}/refine/back_cover`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),

  imageFeedback: (name, step, target, feedback) =>
    request(`/api/projects/${encodeURIComponent(name)}/feedback/image`, {
      method: "POST",
      body: JSON.stringify({ step, target, feedback }),
    }),

  setStyleReference: async (name, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/style-reference`,
      { method: "PUT", body: fd }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  getStyleReferenceInfo: (name) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/style-reference`
    ),

  styleFromImage: async (file, language = "fr") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("language", language);
    const res = await fetch("/api/style-from-image", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      let body;
      try {
        body = await res.json();
      } catch {
        body = { detail: await res.text() };
      }
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  },

  characterFromPhoto: async (file, language = "fr") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("language", language);
    const res = await fetch("/api/character-from-photo", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      let body;
      try {
        body = await res.json();
      } catch {
        body = { detail: await res.text() };
      }
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  },

  setCharacterPhoto: async (name, characterId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(characterId)}/photo`,
      { method: "PUT", body: fd }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteCharacterPhoto: (name, characterId) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(characterId)}/photo`,
      { method: "DELETE" }
    ),

  objectFromPhoto: async (file, language = "fr") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("language", language);
    const res = await fetch("/api/object-from-photo", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      let body;
      try {
        body = await res.json();
      } catch {
        body = { detail: await res.text() };
      }
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  },

  setObjectPhoto: async (name, objectId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(objectId)}/photo`,
      { method: "PUT", body: fd }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteObjectPhoto: (name, objectId) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(objectId)}/photo`,
      { method: "DELETE" }
    ),

  locationFromPhoto: async (file, language = "fr") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("language", language);
    const res = await fetch("/api/location-from-photo", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      let body;
      try {
        body = await res.json();
      } catch {
        body = { detail: await res.text() };
      }
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  },

  setLocationPhoto: async (name, locationId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(locationId)}/photo`,
      { method: "PUT", body: fd }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteLocationPhoto: (name, locationId) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(locationId)}/photo`,
      { method: "DELETE" }
    ),
};

// Subscribe to live progress. Calls onEvent(payload) for each event.
// Returns a function that closes the stream.
export function subscribeJobEvents(onEvent) {
  const src = new EventSource("/api/jobs/current/events");
  src.onmessage = (e) => {
    if (!e.data) return;
    try {
      const payload = JSON.parse(e.data);
      onEvent(payload);
    } catch {
      // ignore non-JSON keepalives
    }
  };
  src.onerror = () => {
    // Browser auto-reconnects; nothing to do.
  };
  return () => src.close();
}
