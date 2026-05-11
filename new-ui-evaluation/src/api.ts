import type {
  ActivityEvent,
  DiagnosticsPayload,
  InboxMessage,
  LiveConnection,
  LiveEvent,
  PreviewData,
  RoundDetail,
  RoundSummary,
  SourceHealth
} from "./types";

const headers = { Accept: "application/json" };
const DEFAULT_STALE_AFTER_MS = 45_000;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "GET", headers });
  if (!response.ok) {
    throw new Error(`Preview request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function fixtureModeRequested(search = window.location.search): boolean {
  const params = new URLSearchParams(search);
  return params.get("fixture") === "1" || params.get("mode") === "fixture";
}

export async function loadPreviewData(options: { fixtureMode?: boolean } = {}): Promise<PreviewData> {
  const path = options.fixtureMode ? "/api/fixtures" : "/api/snapshot";
  const snapshot = await getJson<Omit<PreviewData, "loadedAt">>(path);
  return {
    ...snapshot,
    loadedAt: new Date().toISOString()
  };
}

export function isPreviewDataStale(data: PreviewData, nowMs = Date.now(), staleAfterMs = DEFAULT_STALE_AFTER_MS): boolean {
  if (data.sourceMode === "fixture") {
    return data.connection.status === "fallback";
  }
  const lastSignal = data.connection.lastHeartbeatAt ?? data.generatedAt ?? data.loadedAt;
  const lastSignalMs = Date.parse(lastSignal);
  return Number.isFinite(lastSignalMs) && nowMs - lastSignalMs > staleAfterMs;
}

export function markPreviewDataStale(data: PreviewData, nowMs = Date.now(), staleAfterMs = DEFAULT_STALE_AFTER_MS): PreviewData {
  if (!isPreviewDataStale(data, nowMs, staleAfterMs) || data.connection.status === "failed") {
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

export function applyLiveEvent(data: PreviewData, event: LiveEvent): PreviewData {
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

  let next: PreviewData = {
    ...data,
    cursor: cursor ?? data.cursor,
    connection
  };

  if (event.type === "heartbeat" || event.type === "snapshot_ready") {
    return next;
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

  if (event.type === "round" || event.type === "round_summary") {
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

  if (event.type === "inbox") {
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

  if (event.type === "diagnostics") {
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
  for (const eventName of ["heartbeat", "source_status", "snapshot_ready", "round", "round_summary", "round_removed", "round_detail", "inbox", "activity", "diagnostics", "fallback", "fatal"]) {
    source.addEventListener(eventName, parse as EventListener);
  }
  return source;
}

function upsertBy<T>(items: T[], item: T, key: (item: T) => string): T[] {
  const next = new Map(items.map((existing) => [key(existing), existing]));
  next.set(key(item), item);
  return Array.from(next.values());
}
