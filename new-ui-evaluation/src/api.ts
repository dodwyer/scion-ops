import type {
  ActivityEvent,
  DiagnosticsPayload,
  InboxMessage,
  LiveConnection,
  LiveEvent,
  LiveSnapshot,
  OperatorData,
  RoundDetail,
  RoundSummary,
  RuntimeHealthEventPayload,
  SourceHealth,
  TimelineEntryEventPayload
} from "./types";

const headers = { Accept: "application/json" };
const DEFAULT_STALE_AFTER_MS = 45_000;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "GET", headers });
  if (!response.ok) {
    throw new Error(`Live UI request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function loadOperatorData(): Promise<OperatorData> {
  const snapshot = await getJson<Omit<OperatorData, "loadedAt">>("/api/snapshot");
  return {
    ...snapshot,
    loadedAt: new Date().toISOString()
  };
}

export function isOperatorDataStale(data: OperatorData, nowMs = Date.now(), staleAfterMs = DEFAULT_STALE_AFTER_MS): boolean {
  if (data.sourceMode === "fixture") {
    return data.connection.status === "fallback";
  }
  const lastSignal = data.connection.lastHeartbeatAt ?? data.generatedAt ?? data.loadedAt;
  const lastSignalMs = Date.parse(lastSignal);
  return Number.isFinite(lastSignalMs) && nowMs - lastSignalMs > staleAfterMs;
}

export function markOperatorDataStale(data: OperatorData, nowMs = Date.now(), staleAfterMs = DEFAULT_STALE_AFTER_MS): OperatorData {
  if (!isOperatorDataStale(data, nowMs, staleAfterMs) || data.connection.status === "failed") {
    return data;
  }
  return {
    ...data,
    connection: {
      ...data.connection,
      status: data.connection.status === "fallback" ? "fallback" : "stale"
    },
    overview: {
      ...data.overview,
      freshness: {
        ...data.overview.freshness,
        status: "stale"
      }
    }
  };
}

export function applyLiveEvent(data: OperatorData, event: LiveEvent): OperatorData {
  const cursor = event.cursor ?? event.version ?? event.eventId ?? event.id;
  const connection: LiveConnection = {
    ...data.connection,
    status: event.type === "fatal" ? "failed" : event.type === "fallback" ? "fallback" : "live",
    lastEventId: cursor ?? data.connection.lastEventId,
    lastHeartbeatAt: event.type === "heartbeat" ? event.timestamp : data.connection.lastHeartbeatAt,
    error: event.error ?? null,
    reconnect: {
      ...data.connection.reconnect,
      attempt: 0,
      nextDelaySeconds: undefined
    }
  };

  let next: OperatorData = {
    ...data,
    cursor: cursor ?? data.cursor,
    connection
  };

  if (event.type === "snapshot_ready") {
    const snapshot = getSnapshotReadySnapshot(event.payload);
    if (snapshot) {
      return {
        ...snapshot,
        loadedAt: data.loadedAt,
        cursor: cursor ?? snapshot.cursor ?? data.cursor,
        connection: {
          ...snapshot.connection,
          status: connection.status,
          lastEventId: cursor ?? snapshot.connection.lastEventId ?? data.connection.lastEventId,
          error: connection.error,
          reconnect: {
            ...snapshot.connection.reconnect,
            attempt: 0,
            nextDelaySeconds: undefined
          }
        }
      };
    }
    return next;
  }

  if (event.type === "heartbeat") {
    return next;
  }

  if (event.type === "fallback" || event.type === "fatal") {
    return next;
  }

  if (event.type === "stale" && event.entityId) {
    const sources = next.sourceHealth.map((source) =>
      source.name === event.entityId || source.source === event.entityId
        ? { ...source, status: "stale" as const, stale: true, error: event.error ?? source.error ?? null }
        : source
    );
    return {
      ...next,
      sources,
      sourceHealth: sources,
      runtime: { ...next.runtime, sources }
    };
  }

  if (event.type === "source_status") {
    const source = event.payload as unknown as SourceHealth;
    const sourceName = source.name ?? event.entityId ?? event.source;
    const sources = upsertBy(next.sourceHealth, { ...source, name: String(sourceName) }, (item) => item.name);
    const readiness = sources.map((item) => ({
      source: item.name,
      status: item.status,
      freshnessSeconds: item.freshnessSeconds ?? 0
    }));
    next = {
      ...next,
      sources,
      sourceHealth: sources,
      runtime: { ...next.runtime, sources },
      overview: { ...next.overview, sourceReadiness: readiness },
      diagnostics: {
        ...next.diagnostics,
        sourceHealth: sources,
        sourceErrors: source.error
          ? upsertBy(
              next.diagnostics.sourceErrors,
              {
                source: source.name,
                severity: source.status === "failed" ? "critical" : "warning",
                message: source.error,
                observedAt: event.timestamp
              },
              (item) => item.source
            )
          : next.diagnostics.sourceErrors.filter((item) => item.source !== source.name)
      }
    };
    return next;
  }

  if (event.type === "round" || event.type === "round_summary" || event.type === "round_updated") {
    const round = event.payload as unknown as RoundSummary;
    return { ...next, rounds: upsertBy(next.rounds, round, (item) => item.id) };
  }

  if (event.type === "round_removed" && event.entityId) {
    return {
      ...next,
      rounds: next.rounds.filter((round) => round.id !== event.entityId),
      roundDetails: Object.fromEntries(Object.entries(next.roundDetails).filter(([id]) => id !== event.entityId))
    };
  }

  if (event.type === "round_detail") {
    const detail = event.payload as unknown as RoundDetail;
    return { ...next, roundDetails: { ...next.roundDetails, [detail.id]: detail } };
  }

  if (event.type === "timeline_entry") {
    const payload = event.payload as Partial<TimelineEntryEventPayload>;
    const entry = payload && "entry" in payload
      ? payload.entry
      : event.payload as RoundDetail["timeline"][number];
    const roundId = payload && "roundId" in payload ? payload.roundId : event.entityId;
    if (!roundId || !entry) {
      return next;
    }
    const current = next.roundDetails[roundId];
    if (!current) {
      return next;
    }
    return {
      ...next,
      roundDetails: {
        ...next.roundDetails,
        [roundId]: {
          ...current,
          timeline: upsertBy(current.timeline, entry, (item) => item.id).sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp))
        }
      }
    };
  }

  if (event.type === "inbox" || event.type === "inbox_item") {
    const message = event.payload as unknown as InboxMessage;
    return { ...next, inbox: upsertBy(next.inbox, message, (item) => item.id) };
  }

  if (event.type === "activity") {
    const activity = event.payload as unknown as ActivityEvent;
    return {
      ...next,
      overview: {
        ...next.overview,
        recentActivity: upsertBy(next.overview.recentActivity, activity, (item) => item.id).sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp))
      }
    };
  }

  if (event.type === "runtime_health") {
    const payload = event.payload as Partial<RuntimeHealthEventPayload> | SourceHealth;
    const eventSources = "sources" in payload && Array.isArray(payload.sources)
      ? payload.sources
      : [payload as SourceHealth];
    const sources = eventSources.reduce((items, source) => {
      const sourceName = source.name ?? event.entityId ?? event.source;
      return upsertBy(items, { ...source, name: String(sourceName) }, (item) => item.name);
    }, next.sourceHealth);
    return {
      ...next,
      sources,
      sourceHealth: sources,
      runtime: { ...next.runtime, sources }
    };
  }

  if (event.type === "diagnostics" || event.type === "diagnostic") {
    const diagnostics = event.payload as unknown as DiagnosticsPayload;
    return { ...next, diagnostics: { ...next.diagnostics, ...diagnostics } };
  }

  return next;
}

export function openLiveEventStream(options: {
  streamPath: string;
  cursor: string;
  onEvent: (event: LiveEvent) => void;
  onOpen?: () => void;
  onError?: (error: Event) => void;
  eventSourceCtor?: typeof EventSource;
}): EventSource {
  const url = new URL(options.streamPath, window.location.origin);
  if (options.cursor) {
    url.searchParams.set("cursor", options.cursor);
  }
  const EventSourceCtor = options.eventSourceCtor ?? globalThis.EventSource ?? window.EventSource;
  if (!EventSourceCtor) {
    throw new Error("EventSource is not available in this browser");
  }
  const source = new EventSourceCtor(url.pathname + url.search);
  source.onopen = () => options.onOpen?.();
  source.onerror = (error) => options.onError?.(error);

  const parse = (message: MessageEvent) => {
    try {
      options.onEvent(JSON.parse(message.data) as LiveEvent);
    } catch (error) {
      options.onError?.(new ErrorEvent("error", { error }));
    }
  };

  source.onmessage = parse;
  for (const eventName of [
    "heartbeat",
    "source_status",
    "snapshot_ready",
    "round",
    "round_summary",
    "round_updated",
    "round_removed",
    "round_detail",
    "timeline_entry",
    "inbox",
    "inbox_item",
    "activity",
    "runtime_health",
    "diagnostics",
    "diagnostic",
    "stale",
    "fallback",
    "fatal"
  ]) {
    source.addEventListener(eventName, parse as EventListener);
  }
  return source;
}

function upsertBy<T>(items: T[], item: T, key: (item: T) => string): T[] {
  const next = new Map(items.map((existing) => [key(existing), existing]));
  next.set(key(item), item);
  return Array.from(next.values());
}

function getSnapshotReadySnapshot(payload: unknown): LiveSnapshot | null {
  if (!isRecord(payload) || !isRecord(payload.snapshot)) {
    return null;
  }
  const snapshot = payload.snapshot;
  if (
    typeof snapshot.schemaVersion !== "string" ||
    typeof snapshot.sourceMode !== "string" ||
    typeof snapshot.fixtureBacked !== "boolean" ||
    typeof snapshot.generatedAt !== "string" ||
    typeof snapshot.cursor !== "string" ||
    !Array.isArray(snapshot.rounds) ||
    !isRecord(snapshot.roundDetails) ||
    !Array.isArray(snapshot.inbox) ||
    !isRecord(snapshot.overview) ||
    !isRecord(snapshot.runtime) ||
    !isRecord(snapshot.diagnostics) ||
    !Array.isArray(snapshot.sources) ||
    !Array.isArray(snapshot.sourceHealth) ||
    !isRecord(snapshot.connection)
  ) {
    return null;
  }
  return snapshot as unknown as LiveSnapshot;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
