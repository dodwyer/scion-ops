import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../fixtures/local-fixtures.json";
import { applyLiveEvent, loadOperatorData, markOperatorDataStale, openLiveEventStream } from "../api";
import { App } from "../App";
import type { LiveEvent, LiveSnapshot, OperatorData, OperatorFixtures, RuntimeHealthEventPayload, SourceHealth, TimelineEntryEventPayload } from "../types";

const typedFixtures = fixtures as OperatorFixtures;

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
  fixtureBacked: false,
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
    fixtureBacked: false,
    sourceMode: "live",
    summary: "Live read-only operator console snapshot",
    sourceReadiness: liveSources.map((source) => ({ source: source.name, status: source.status, freshnessSeconds: source.freshnessSeconds ?? 0 }))
  },
  runtime: {
    sources: liveSources,
    liveService: {
      name: "scion-ops-web-app",
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
    schemaVersion: "scion-ops-web-app.live.v1",
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

describe("live UI contract", () => {
  it("keeps fixture data explicit and read-only", () => {
    expect(typedFixtures.fixtureBacked).toBe(true);
    expect(typedFixtures.overview.fixtureBacked).toBe(true);
    expect(typedFixtures.runtime.liveService.fixtureOnly).toBe(true);
    expect(typedFixtures.runtime.liveService.liveReadsAllowed).toBe(false);
    expect(typedFixtures.runtime.liveService.mutationsAllowed).toBe(false);
  });

  it("loads the live snapshot endpoint by default", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(liveSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    const data = await loadOperatorData();

    expect(data.sourceMode).toBe("live");
    expect(data.runtime.liveService.streamPath).toBe("/api/events");
    expect(fetchMock).toHaveBeenCalledWith("/api/snapshot", expect.objectContaining({ method: "GET" }));
  });

  it("uses fixture fallback only when explicitly requested", async () => {
    const fixtureSnapshot = { ...liveSnapshot, sourceMode: "fixture", fixtureBacked: true };
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(fixtureSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    await loadOperatorData({ fixtureMode: true });

    expect(fetchMock).toHaveBeenCalledWith("/api/fixtures", expect.objectContaining({ method: "GET" }));
  });

  it("renders live connection and source staleness from snapshot", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(liveSnapshot)));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => expect(screen.getByText("Operator Console")).toBeInTheDocument());
    expect(screen.getByText(/SSE updates via \/api\/events/i)).toBeInTheDocument();
    expect(screen.getByText("Git need attention")).toBeInTheDocument();
  });

  it("merges replayed events idempotently and preserves existing data", () => {
    const initial: OperatorData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const event: LiveEvent<SourceHealth> = {
      schemaVersion: "scion-ops-web-app.event.v1",
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

  it("replaces stale data from snapshot_ready payload snapshots", () => {
    const initial: OperatorData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const recoveredSnapshot: LiveSnapshot = {
      ...liveSnapshot,
      generatedAt: "2026-05-11T15:41:30Z",
      cursor: "snapshot-cursor",
      rounds: [{ ...liveSnapshot.rounds[0], id: "round-recovered", goal: "Recovered round from snapshot" }],
      roundDetails: {},
      inbox: [],
      connection: {
        ...liveSnapshot.connection,
        status: "reconnecting",
        lastEventId: "snapshot-cursor",
        reconnect: { ...liveSnapshot.connection.reconnect, attempt: 3, nextDelaySeconds: 10 },
        error: "previous snapshot error"
      }
    };
    const event: LiveEvent<{ snapshot: LiveSnapshot }> = {
      schemaVersion: "scion-ops-web-app.event.v1",
      type: "snapshot_ready",
      id: "evt-snapshot-ready",
      eventId: "evt-snapshot-ready",
      source: "Adapter",
      timestamp: "2026-05-11T15:41:31Z",
      cursor: "cursor-recovery",
      payload: { snapshot: recoveredSnapshot }
    };

    const next = applyLiveEvent(initial, event);

    expect(next.loadedAt).toBe(initial.loadedAt);
    expect(next.generatedAt).toBe(recoveredSnapshot.generatedAt);
    expect(next.rounds).toEqual(recoveredSnapshot.rounds);
    expect(next.roundDetails).toEqual({});
    expect(next.inbox).toEqual([]);
    expect(next.cursor).toBe("cursor-recovery");
    expect(next.connection.status).toBe("live");
    expect(next.connection.lastEventId).toBe("cursor-recovery");
    expect(next.connection.reconnect.attempt).toBe(0);
    expect(next.connection.reconnect.nextDelaySeconds).toBeUndefined();
    expect(next.connection.error).toBeNull();
  });

  it("merges backend timeline entry events by payload round id", () => {
    const initial: OperatorData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const roundId = initial.rounds[0].id;
    const entry = {
      id: "timeline-entry-live",
      timestamp: "2026-05-11T15:41:10Z",
      actor: "Adapter",
      kind: "event",
      summary: "Live timeline update"
    };
    const event: LiveEvent<TimelineEntryEventPayload> = {
      schemaVersion: "scion-ops-web-app.event.v1",
      type: "timeline_entry",
      id: "evt-timeline-entry-live",
      eventId: "evt-timeline-entry-live",
      entityId: entry.id,
      source: "Adapter",
      timestamp: "2026-05-11T15:41:10Z",
      cursor: "cursor-2",
      payload: { roundId, entry }
    };

    const once = applyLiveEvent(initial, event);
    const twice = applyLiveEvent(once, event);
    const timeline = twice.roundDetails[roundId].timeline;

    expect(timeline.filter((item) => item.id === entry.id)).toHaveLength(1);
    expect(timeline[timeline.length - 1]).toEqual(entry);
    expect(twice.rounds).toHaveLength(initial.rounds.length);
  });

  it("merges backend runtime health source aggregates idempotently", () => {
    const initial: OperatorData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const sources: SourceHealth[] = [
      { ...liveSources[0], status: "degraded", detail: "hub probe delayed", freshnessSeconds: 15 },
      { ...liveSources[1], status: "healthy", detail: "branch read recovered", stale: false, error: null }
    ];
    const event: LiveEvent<RuntimeHealthEventPayload> = {
      schemaVersion: "scion-ops-web-app.event.v1",
      type: "runtime_health",
      id: "evt-runtime-health",
      eventId: "evt-runtime-health",
      source: "Adapter",
      timestamp: "2026-05-11T15:41:20Z",
      cursor: "cursor-3",
      payload: { sources }
    };

    const once = applyLiveEvent(initial, event);
    const twice = applyLiveEvent(once, event);

    expect(twice.sourceHealth.filter((source) => source.name === "Hub")).toHaveLength(1);
    expect(twice.sourceHealth.filter((source) => source.name === "Git")).toHaveLength(1);
    expect(twice.sourceHealth.find((source) => source.name === "Hub")?.detail).toBe("hub probe delayed");
    expect(twice.runtime.sources.find((source) => source.name === "Git")?.status).toBe("healthy");
  });

  it("marks preserved data stale when heartbeats age out", () => {
    const initial: OperatorData = { ...liveSnapshot, loadedAt: "2026-05-11T15:40:51Z" };
    const stale = markOperatorDataStale(initial, Date.parse("2026-05-11T15:42:00Z"), 10_000);

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
      schemaVersion: "scion-ops-web-app.event.v1",
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
