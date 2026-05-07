import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { api, subscribeJobEvents } from "./api.js";

function jsonResponse(data, { status = 200 } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

function errorResponse({ status, statusText = "", json, text }) {
  return {
    ok: false,
    status,
    statusText,
    json: async () => {
      if (json !== undefined) return json;
      throw new SyntaxError("not json");
    },
    text: async () => text ?? "",
  };
}

describe("request helper (via api.health)", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on a 200 response", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "ok" }));

    const result = await api.health();

    expect(result).toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.any(Object));
  });

  it("returns null on 204 No Content", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error("no body");
      },
    });

    expect(await api.lockSecretsVault()).toBeNull();
  });

  it("throws Error with status and body when response has a JSON detail", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse({ status: 400, statusText: "Bad Request", json: { detail: "missing field" } }),
    );

    await expect(api.health()).rejects.toMatchObject({
      message: "missing field",
      status: 400,
      body: { detail: "missing field" },
    });
  });

  it("falls back to response text when body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse({ status: 500, statusText: "Server Error", text: "Internal Server Error" }),
    );

    await expect(api.health()).rejects.toMatchObject({
      message: "Internal Server Error",
      status: 500,
      body: { detail: "Internal Server Error" },
    });
  });

  it("uses statusText when no detail is available", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse({ status: 404, statusText: "Not Found", json: {} }));

    await expect(api.health()).rejects.toMatchObject({ message: "Not Found", status: 404 });
  });

  it("sends Content-Type application/json by default", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}));

    await api.health();

    const opts = fetchMock.mock.calls[0][1];
    expect(opts.headers["Content-Type"]).toBe("application/json");
  });
});

describe("URL construction and encoding", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("URL-encodes project names with reserved characters", async () => {
    await api.getProject("my project / with / slashes");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/projects/my%20project%20%2F%20with%20%2F%20slashes",
    );
  });

  it("builds the export URL without making a request", () => {
    expect(api.exportUrl("hello world")).toBe("/api/projects/hello%20world/export");
  });

  it("serializes the JSON body for POST requests", async () => {
    await api.createProject({ name: "demo" });

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "demo" }));
  });

  it("uses DELETE method for deleteProject", async () => {
    await api.deleteProject("foo");

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects/foo");
    expect(opts.method).toBe("DELETE");
  });

  it("renames duplicateProject options to snake_case", async () => {
    await api.duplicateProject("src", {
      newProject: "dst",
      includeReferences: true,
      includePhotos: false,
      includeStyleReference: false,
    });

    const opts = fetchMock.mock.calls[0][1];
    expect(JSON.parse(opts.body)).toEqual({
      new_project: "dst",
      include_references: true,
      include_photos: false,
      include_style_reference: false,
    });
  });

  it("duplicateProject defaults send conservative inclusion flags", async () => {
    await api.duplicateProject("src");

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      new_project: null,
      include_references: false,
      include_photos: true,
      include_style_reference: true,
    });
  });

  it("encodes IDs in deeply nested URLs", async () => {
    await api.refineCharacter("p", "id with spaces", "feedback text");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p/refine/character/id%20with%20spaces");
  });

  it("upgradeQuality forces high quality on the listed targets", async () => {
    await api.upgradeQuality("p", "references", ["a", "b"]);

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      force_ids: ["a", "b"],
      quality_override: "high",
    });
  });

  it("regenerateAll omits quality_override when none is provided", async () => {
    await api.regenerateAll("p", "references");

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ force_all: true });
  });

  it("deleteCharacter encodes auto_regenerate flag in the query string", async () => {
    await api.deleteCharacter("p", "id with space", false);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/projects/p/characters/id%20with%20space?auto_regenerate=false",
    );
  });
});

describe("FormData endpoints", () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends file via multipart/form-data without an explicit Content-Type", async () => {
    const file = new Blob(["x"], { type: "text/plain" });

    await api.importProject(file);

    const opts = fetchMock.mock.calls[0][1];
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
    // Content-Type must come from the browser so it includes the boundary.
    expect(opts.headers).toBeUndefined();
  });

  it("propagates the response text on FormData endpoint failure", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      text: async () => "Bad upload",
    });

    await expect(api.importProject(new Blob(["x"]))).rejects.toThrow("Bad upload");
  });

  it("exportReferencesBundle returns a Blob on success", async () => {
    const fakeBlob = new Blob(["zip"]);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: async () => fakeBlob,
    });

    const result = await api.exportReferencesBundle("p", { characters: ["a"] });

    expect(result).toBe(fakeBlob);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects/p/references/export");
    expect(opts.method).toBe("POST");
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(opts.body)).toEqual({ characters: ["a"] });
  });

  it("exportReferencesBundle reports JSON detail on failure", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse({ status: 422, statusText: "Unprocessable", json: { detail: "no refs" } }),
    );

    await expect(api.exportReferencesBundle("p", {})).rejects.toThrow("no refs");
  });
});

describe("subscribeJobEvents", () => {
  let lastSource;

  beforeEach(() => {
    class FakeEventSource {
      constructor(url) {
        this.url = url;
        this.onmessage = null;
        this.onerror = null;
        this.closed = false;
        lastSource = this;
      }
      close() {
        this.closed = true;
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    lastSource = undefined;
  });

  it("opens an EventSource on the events endpoint and returns a closer", () => {
    const cleanup = subscribeJobEvents(() => {});

    expect(lastSource.url).toBe("/api/jobs/current/events");
    cleanup();
    expect(lastSource.closed).toBe(true);
  });

  it("parses JSON payloads and forwards to the callback", () => {
    const onEvent = vi.fn();
    subscribeJobEvents(onEvent);

    lastSource.onmessage({ data: JSON.stringify({ type: "progress", message: "hi" }) });

    expect(onEvent).toHaveBeenCalledWith({ type: "progress", message: "hi" });
  });

  it("ignores empty data lines (keepalives)", () => {
    const onEvent = vi.fn();
    subscribeJobEvents(onEvent);

    lastSource.onmessage({ data: "" });

    expect(onEvent).not.toHaveBeenCalled();
  });

  it("ignores non-JSON payloads", () => {
    const onEvent = vi.fn();
    subscribeJobEvents(onEvent);

    lastSource.onmessage({ data: "not json {[" });

    expect(onEvent).not.toHaveBeenCalled();
  });

  it("installs an onerror handler that does not throw", () => {
    subscribeJobEvents(() => {});

    expect(() => lastSource.onerror({})).not.toThrow();
  });
});
