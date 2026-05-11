import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../fixtures/preview-fixtures.json";
import { applyLiveEvent, loadPreviewData, markPreviewDataStale, openLiveEventStream } from "../api";
import { App } from "../App";
import type { LiveEvent, LiveSnapshot, PreviewData, PreviewFixtures, SourceHealth } from "../types";

const typedFixtures = fixtures as PreviewFixtures;

const liveSources: SourceHealth[] = [
  {
    name: "Hub",
    kind: "control-plane",
    status: "healthy",
    detail: "sessions discovered",
    lastSeen: "2026-05-11T15:40:50Z",
    lastSuccessfulUpdate: "2026-05-11T15:40:50Z",
    freshnessSeconds: 2,
    stale: false,
    sourceMode: "live"
  },
  {
    name: "Git",
    kind: "source",
    status: "stale",
    detail: "branch read is old",
    lastSeen: "2026-05-11T15:30:00Z",
    lastSuccessfulUpdate: "2026-05-11T15:30:00Z",
    freshnessSeconds: 650,
    stale: true,
    sourceMode: "live",
    error: "git read delayed"
  }
];

const liveSnapshot: LiveSnapshot = {
  ...typedFixtures,
  mocked: false,
  sourceMode: "live",
  generatedAt: "2026-05-11T15:40:50Z",
  cursor: "cursor-1",
  sources: liveSources,
  sourceHealth: liveSources,
  connection: {
    status: "live",
    transport: "sse",
    lastEventId: "cursor-1",
    lastHeartbeatAt: "2026-05-11T15:40:50Z",
    reconnect: { supported: true, maxBackoffSeconds: 30, resumeParam: "cursor" }
  },
  overview: {
    ...typedFixtures.overview,
    mocked: false,
    sourceMode: "live",
    summary: "Live read-only operator console snapshot",
    sourceReadiness: liveSources.map((source) => ({ source: source.name, status: source.status, freshnessSeconds: source.freshnessSeconds ?? 0 }))
  },
  runtime: {
    sources: liveSources,
    previewService: {
      name: "scion-ops-new-ui-eval",
      port: 8091,
      healthPath: "/healthz",
      fixtureOnly: false,
      liveReadsAllowed: true,
      mutationsAllowed: false,
      sourceMode: "live",
      streamPath: "/api/events",
      snapshotPath: "/api/snapshot"
    }
  },
  diagnostics: {
    ...typedFixtures.diagnostics,
    schemaVersion: "new-ui-evaluation.live.v1",
    sourceMode: "live",
    sourceHealth: liveSources,
    sourceErrors: [{ source: "Git", severity: "warning", message: "git read delayed", observedAt: "2026-05-11T15:40:50Z" }]
  }
};

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  listeners = new Map<string, EventListener[]>();
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, payload: unknown) {
    const event = new MessageEvent(type, { data: JSON.stringify(payload) });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  MockEventSource.instances = [];
});

describe("preview live contract", () => {
  it("keeps fixture data explicit and read-only", () => {
    expect(typedFixtures.mocked).toBe(true);
    expect(typedFixtures.overview.mocked).toBe(true);
    expect(typedFixtures.runtime.previewService.fixtureOnly).toBe(true);
    expect(typedFixtures.runtime.previewService.liveReadsAllowed).toBe(false);
    expect(typedFixtures.runtime.previewService.mutationsAllowed).toBe(false);
  });

  it("loads the live snapshot endpoint by default", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(liveSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    const data = await loadPreviewData();

    expect(data.sourceMode).toBe("live");
    expect(data.runtime.previewService.streamPath).toBe("/api/events");
    expect(fetchMock).toHaveBeenCalledWith("/api/snapshot", expect.objectContaining({ method: "GET" }));
  });

  it("uses fixture fallback only when explicitly requested", async () => {
    const fixtureSnapshot = { ...liveSnapshot, sourceMode: "fixture", mocked: true };
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(fixtureSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    await loadPreviewData({ fixtureMode: true });

    expect(fetchMock).toHaveBeenCalledWith("/api/fixtures", expect.objectContaining({ method: "GET" }));
  });

  it("renders live connection and source staleness from snapshot", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(liveSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => expect(screen.getByText("Preview Console")).toBeInTheDocument());
    expect(screen.getByText(/SSE updates via \/api\/events/i)).toBeInTheDocument();
    expect(screen.getByText("Git need attention")).toBeInTheDocument();
  });

  it("merges replayed events idempotently and preserves existing data", () => {
    const initial: PreviewData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const event: LiveEvent<SourceHealth> = {
      schemaVersion: "new-ui-evaluation.event.v1",
      type: "source_status",
      id: "evt-git",
      eventId: "evt-git",
      entityId: "Git",
      source: "Git",
      timestamp: "2026-05-11T15:41:00Z",
      cursor: "cursor-2",
      payload: { ...liveSources[1], status: "degraded", stale: true, error: "kubectl read failed" }
    };

    const once = applyLiveEvent(initial, event);
    const twice = applyLiveEvent(once, event);

    expect(twice.sourceHealth.filter((source) => source.name === "Git")).toHaveLength(1);
    expect(twice.runtime.sources.filter((source) => source.name === "Git")).toHaveLength(1);
    expect(twice.diagnostics.sourceErrors.filter((error) => error.source === "Git")).toHaveLength(1);
    expect(twice.rounds).toHaveLength(initial.rounds.length);
  });

  it("marks preserved data stale when heartbeats age out", () => {
    const initial: PreviewData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const stale = markPreviewDataStale(initial, Date.parse("2026-05-11T15:42:00Z"), 10_000);

    expect(stale.connection.status).toBe("stale");
    expect(stale.overview.freshness.status).toBe("stale");
    expect(stale.rounds).toEqual(initial.rounds);
  });

  it("opens the SSE stream with the latest cursor for resume", () => {
    const received: LiveEvent[] = [];
    const source = openLiveEventStream({
      streamPath: "/api/events",
      cursor: "cursor-1",
      eventSourceCtor: MockEventSource as unknown as typeof EventSource,
      onEvent: (event) => received.push(event)
    });
    const event: LiveEvent = {
      schemaVersion: "new-ui-evaluation.event.v1",
      type: "heartbeat",
      id: "evt-heartbeat",
      source: "Adapter",
      timestamp: "2026-05-11T15:41:00Z",
      cursor: "cursor-2",
      payload: { status: "live" }
    };

    MockEventSource.instances[0].emit("heartbeat", event);

    expect(source).toBe(MockEventSource.instances[0]);
    expect(MockEventSource.instances[0].url).toBe("/api/events?cursor=cursor-1");
    expect(received[0]).toEqual(event);
  });
});
