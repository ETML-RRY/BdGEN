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
  // Some endpoints can be served by the SPA fallback when the backend
  // doesn't know the route (typically when the server was started before
  // a new endpoint was added). Detecting HTML here gives a clear,
  // actionable error instead of a cryptic JSON parse failure.
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("json")) {
    const peek = (await res.text()).slice(0, 80);
    if (peek.trim().toLowerCase().startsWith("<!doctype") || peek.includes("<html")) {
      // The backend doesn't know this route — the SPA fallback served HTML
      // instead. We surface a structured error so the caller can translate
      // it; the `path` is preserved for the user-facing message.
      const err = new Error(path);
      err.status = 404;
      err.kind = "unknownEndpoint";
      err.path = path;
      err.body = { detail: peek };
      throw err;
    }
  }
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  secretsStatus: () => request("/api/secrets/status"),
  createSecretsVault: (password, secrets, overwrite = false) =>
    request("/api/secrets/create", {
      method: "POST",
      body: JSON.stringify({ password, secrets, overwrite }),
    }),
  unlockSecretsVault: async (password) => {
    try {
      return await request("/api/secrets/unlock", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
    } catch (e) {
      // 401 = wrong password or corrupted vault (server raises
      // `Mot de passe incorrect ou coffre illisible.`). Tag the error so the
      // UI can translate it instead of showing the raw French message.
      if (e && e.status === 401) e.kind = "wrongPassword";
      throw e;
    }
  },
  lockSecretsVault: () => request("/api/secrets/lock", { method: "POST" }),
  updateSecretProvider: (provider, value, password = null) =>
    request(`/api/secrets/providers/${encodeURIComponent(provider)}`, {
      method: "PUT",
      body: JSON.stringify({ value, password }),
    }),

  listProjects: () => request("/api/projects"),
  getProject: (name) => request(`/api/projects/${encodeURIComponent(name)}`),
  getProjectStatistics: (name) => request(`/api/projects/${encodeURIComponent(name)}/statistics`),
  createProject: (config) => request("/api/projects", { method: "POST", body: JSON.stringify(config) }),
  quickCreate: async (prompt, { language = "fr", files = [], artStyle = "" } = {}) => {
    const fd = new FormData();
    fd.append("prompt", prompt);
    fd.append("language", language);
    fd.append("art_style", artStyle);
    for (const file of files) fd.append("files", file);
    const res = await fetch("/api/quick-create", { method: "POST", body: fd });
    if (!res.ok) {
      let body;
      try {
        body = await res.json();
      } catch {
        body = { detail: await res.text() };
      }
      const err = new Error(body.detail || res.statusText);
      err.status = res.status;
      throw err;
    }
    return res.json();
  },
  updateProject: (name, config) =>
    request(`/api/projects/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  deleteProject: (name) => request(`/api/projects/${encodeURIComponent(name)}`, { method: "DELETE" }),
  duplicateProject: (
    name,
    {
      newProject = null,
      newTitle = null,
      includeReferences = false,
      includePhotos = true,
      includeStyleReference = true,
    } = {},
  ) =>
    request(`/api/projects/${encodeURIComponent(name)}/duplicate`, {
      method: "POST",
      body: JSON.stringify({
        new_project: newProject,
        new_title: newTitle,
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

  // Dev-only trace endpoints. Return 404 in production (when BDGEN_DEBUG is off).
  debugEnabled: () => request("/api/debug/enabled"),
  listTraces: (name) => request(`/api/projects/${encodeURIComponent(name)}/traces`),
  getTrace: (name, sessionId) =>
    request(`/api/projects/${encodeURIComponent(name)}/traces/${encodeURIComponent(sessionId)}`),

  // File version history. `path` is the project-relative path of the live
  // artefact (e.g. "pages/page_03.png"). Each archive entry has a
  // `version_id` (ISO timestamp) and a `relpath` to fetch its bytes via the
  // /files endpoint.
  listVersions: (name, path) => {
    const encoded = path.split("/").map(encodeURIComponent).join("/");
    return request(`/api/projects/${encodeURIComponent(name)}/versions/${encoded}`);
  },
  restoreVersion: (name, path, versionId) => {
    const encoded = path.split("/").map(encodeURIComponent).join("/");
    return request(`/api/projects/${encodeURIComponent(name)}/versions/${encoded}/restore`, {
      method: "POST",
      body: JSON.stringify({ version_id: versionId }),
    });
  },

  exportUrl: (name) => `/api/projects/${encodeURIComponent(name)}/export`,
  importProject: async (file, { newProject = null, newTitle = null } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (newProject) fd.append("new_project", newProject);
    if (newTitle) fd.append("new_title", newTitle);
    const res = await fetch("/api/projects/import", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  listExportableReferences: (name) => request(`/api/projects/${encodeURIComponent(name)}/references/exportable`),
  exportReferencesBundle: async (name, picks) => {
    const res = await fetch(`/api/projects/${encodeURIComponent(name)}/references/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(picks),
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
    return res.blob();
  },
  importReferencesBundle: async (name, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(name)}/references/import`, {
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

  currentJob: () => request("/api/jobs/current"),
  interruptJob: () => request("/api/jobs/current/interrupt", { method: "POST" }),
  clearJob: () => request("/api/jobs/current/clear", { method: "POST" }),

  startStep: (name, step, payload = {}) =>
    request(`/api/projects/${encodeURIComponent(name)}/steps/${step}/start`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  regenerateAll: (name, step) =>
    request(`/api/projects/${encodeURIComponent(name)}/steps/${step}/start`, {
      method: "POST",
      body: JSON.stringify({ force_all: true }),
    }),

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
  updateScriptPage: (name, n, page) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/pages/${n}`, {
      method: "PUT",
      body: JSON.stringify(page),
    }),
  getConfigScriptDiff: (name) => request(`/api/projects/${encodeURIComponent(name)}/script/config-diff`),

  syncScriptWithConfig: (name, removals = null) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/sync-config`, {
      method: "POST",
      body: JSON.stringify(removals ? { removals } : {}),
    }),

  checkScriptCoherence: (name) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/coherence/check`, {
      method: "POST",
    }),
  updateScriptCharacter: (name, id, character) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/characters/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(character),
    }),
  addScriptCharacter: (name, character) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/characters`, {
      method: "POST",
      body: JSON.stringify(character),
    }),
  updateScriptLocation: (name, id, location) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/locations/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(location),
    }),
  addScriptLocation: (name, location) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/locations`, {
      method: "POST",
      body: JSON.stringify(location),
    }),
  updateScriptObject: (name, id, object) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/objects/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(object),
    }),
  addScriptObject: (name, object) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/objects`, {
      method: "POST",
      body: JSON.stringify(object),
    }),
  updateScriptCover: (name, cover) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/cover`, {
      method: "PUT",
      body: JSON.stringify(cover),
    }),
  updateScriptBackCover: (name, backCover) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/back-cover`, {
      method: "PUT",
      body: JSON.stringify(backCover),
    }),
  applyGlobalSuggestion: (name, suggestion) =>
    request(`/api/projects/${encodeURIComponent(name)}/script/suggestions/apply`, {
      method: "POST",
      body: JSON.stringify({ suggestion }),
    }),
  previewDeleteCharacter: (name, id) =>
    request(`/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(id)}/delete-preview`),
  previewDeleteLocation: (name, id) =>
    request(`/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(id)}/delete-preview`),
  previewDeleteObject: (name, id) =>
    request(`/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(id)}/delete-preview`),
  deleteCharacter: (name, id, autoRegenerate = true) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(id)}?auto_regenerate=${autoRegenerate}`,
      { method: "DELETE" },
    ),
  deleteLocation: (name, id, autoRegenerate = true) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(id)}?auto_regenerate=${autoRegenerate}`,
      { method: "DELETE" },
    ),
  deleteObject: (name, id, autoRegenerate = true) =>
    request(
      `/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(id)}?auto_regenerate=${autoRegenerate}`,
      { method: "DELETE" },
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

  inpaintImage: async (name, step, targetId, maskBlob, prompt) => {
    const fd = new FormData();
    fd.append("prompt", prompt);
    fd.append("mask", maskBlob, "mask.png");
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/inpaint/${encodeURIComponent(step)}/${encodeURIComponent(targetId)}`,
      { method: "POST", body: fd },
    );
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

  setStyleReference: async (name, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(name)}/style-reference`, { method: "PUT", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  getStyleReferenceInfo: (name) => request(`/api/projects/${encodeURIComponent(name)}/style-reference`),

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
      { method: "PUT", body: fd },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteCharacterPhoto: (name, characterId) =>
    request(`/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(characterId)}/photo`, {
      method: "DELETE",
    }),

  addCharacterPhoto: async (name, characterId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(characterId)}/photos`,
      { method: "POST", body: fd },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteCharacterPhotoSlot: (name, characterId, slot) =>
    request(`/api/projects/${encodeURIComponent(name)}/characters/${encodeURIComponent(characterId)}/photos/${slot}`, {
      method: "DELETE",
    }),

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
    const res = await fetch(`/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(objectId)}/photo`, {
      method: "PUT",
      body: fd,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteObjectPhoto: (name, objectId) =>
    request(`/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(objectId)}/photo`, {
      method: "DELETE",
    }),

  addObjectPhoto: async (name, objectId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(objectId)}/photos`,
      { method: "POST", body: fd },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteObjectPhotoSlot: (name, objectId, slot) =>
    request(`/api/projects/${encodeURIComponent(name)}/objects/${encodeURIComponent(objectId)}/photos/${slot}`, {
      method: "DELETE",
    }),

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
      { method: "PUT", body: fd },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteLocationPhoto: (name, locationId) =>
    request(`/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(locationId)}/photo`, {
      method: "DELETE",
    }),

  addLocationPhoto: async (name, locationId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(locationId)}/photos`,
      { method: "POST", body: fd },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  deleteLocationPhotoSlot: (name, locationId, slot) =>
    request(`/api/projects/${encodeURIComponent(name)}/locations/${encodeURIComponent(locationId)}/photos/${slot}`, {
      method: "DELETE",
    }),
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
