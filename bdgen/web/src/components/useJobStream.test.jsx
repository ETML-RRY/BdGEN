import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

const { subscribeMock, currentJobMock, interruptJobMock, clearJobMock } = vi.hoisted(() => ({
  subscribeMock: vi.fn(),
  currentJobMock: vi.fn(),
  interruptJobMock: vi.fn(),
  clearJobMock: vi.fn(),
}));

vi.mock("../api.js", () => ({
  api: {
    currentJob: currentJobMock,
    interruptJob: interruptJobMock,
    clearJob: clearJobMock,
  },
  subscribeJobEvents: subscribeMock,
}));

import useJobStream from "./useJobStream";

function latestEventHandler() {
  const calls = subscribeMock.mock.calls;
  return calls[calls.length - 1][0];
}

describe("useJobStream", () => {
  beforeEach(() => {
    subscribeMock.mockReset();
    currentJobMock.mockReset();
    interruptJobMock.mockReset();
    clearJobMock.mockReset();

    subscribeMock.mockImplementation(() => () => {});
    currentJobMock.mockResolvedValue({ job: null });
  });

  it("fetches the current job on mount", async () => {
    currentJobMock.mockResolvedValueOnce({ job: { project: "p", step: "s" } });

    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));

    await waitFor(() => expect(result.current.job).toEqual({ project: "p", step: "s" }));
    expect(currentJobMock).toHaveBeenCalled();
  });

  it("subscribes on mount and tears down on unmount", () => {
    const cleanup = vi.fn();
    subscribeMock.mockReturnValue(cleanup);

    const { unmount } = renderHook(() => useJobStream({ project: "p", step: "s" }));

    expect(subscribeMock).toHaveBeenCalledTimes(1);
    unmount();
    expect(cleanup).toHaveBeenCalled();
  });

  it("appends progress events to the events array", async () => {
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));
    await waitFor(() => expect(subscribeMock).toHaveBeenCalled());

    act(() => {
      latestEventHandler()({ type: "progress", message: "step 1", current: 1, total: 3 });
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0]).toMatchObject({ message: "step 1", current: 1, total: 3 });
  });

  it("caps the events array at 200 entries (oldest dropped first)", async () => {
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));
    await waitFor(() => expect(subscribeMock).toHaveBeenCalled());
    const onEvent = latestEventHandler();

    act(() => {
      for (let i = 0; i < 250; i += 1) {
        onEvent({ type: "progress", message: `m${i}` });
      }
    });

    expect(result.current.events).toHaveLength(200);
    expect(result.current.events[0].message).toBe("m50");
    expect(result.current.events[199].message).toBe("m249");
  });

  it("merges progress data into the cached job snapshot", async () => {
    currentJobMock.mockResolvedValueOnce({
      job: { project: "p", step: "s", progress_current: 0, progress_total: 5 },
    });
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));
    await waitFor(() => expect(result.current.job).not.toBeNull());

    act(() => {
      latestEventHandler()({ type: "progress", message: "halfway", current: 3, total: 5 });
    });

    expect(result.current.job.last_message).toBe("halfway");
    expect(result.current.job.progress_current).toBe(3);
    expect(result.current.job.progress_total).toBe(5);
  });

  it("ignores progress events when there is no cached job snapshot", async () => {
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));
    await waitFor(() => expect(subscribeMock).toHaveBeenCalled());

    act(() => {
      latestEventHandler()({ type: "progress", message: "stray" });
    });

    // Event still gets pushed to the events array, but job stays null.
    expect(result.current.job).toBeNull();
    expect(result.current.events).toHaveLength(1);
  });

  it("sets terminal state and refreshes on terminal events", async () => {
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));
    await waitFor(() => expect(subscribeMock).toHaveBeenCalled());

    currentJobMock.mockClear();
    currentJobMock.mockResolvedValueOnce({ job: null });

    act(() => {
      latestEventHandler()({ type: "terminal", status: "success", message: "done" });
    });

    expect(result.current.terminal).toEqual({ type: "terminal", status: "success", message: "done" });
    await waitFor(() => expect(currentJobMock).toHaveBeenCalled());
  });

  it("interrupt() calls api.interruptJob", async () => {
    interruptJobMock.mockResolvedValue(null);
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));

    await act(async () => {
      await result.current.interrupt();
    });

    expect(interruptJobMock).toHaveBeenCalledTimes(1);
  });

  it("clear() resets state and calls api.clearJob", async () => {
    clearJobMock.mockResolvedValue(null);
    currentJobMock.mockResolvedValueOnce({ job: { project: "p", step: "s" } });
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));
    await waitFor(() => expect(result.current.job).not.toBeNull());

    act(() => {
      latestEventHandler()({ type: "progress", message: "noise" });
    });
    expect(result.current.events.length).toBeGreaterThan(0);

    await act(async () => {
      await result.current.clear();
    });

    expect(clearJobMock).toHaveBeenCalledTimes(1);
    expect(result.current.job).toBeNull();
    expect(result.current.events).toEqual([]);
    expect(result.current.terminal).toBeNull();
  });

  it("matchesThisStep is true when project and step align with the cached job", async () => {
    currentJobMock.mockResolvedValueOnce({ job: { project: "p", step: "s" } });
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));

    await waitFor(() => expect(result.current.job).not.toBeNull());
    expect(result.current.matchesThisStep).toBe(true);
  });

  it("matchesThisStep is false when the cached job mismatches", async () => {
    currentJobMock.mockResolvedValueOnce({ job: { project: "other", step: "s" } });
    const { result } = renderHook(() => useJobStream({ project: "p", step: "s" }));

    await waitFor(() => expect(result.current.job).not.toBeNull());
    expect(result.current.matchesThisStep).toBe(false);
  });
});
