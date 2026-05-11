export type Status =
  | "healthy"
  | "degraded"
  | "stale"
  | "mocked"
  | "live"
  | "reconnecting"
  | "fallback"
  | "blocked"
  | "active"
  | "completed"
  | "failed"
  | "empty"
  | "passed"
  | "running"
  | "waiting"
  | "not-started"
  | "accepted";

export type Severity = "info" | "warning" | "critical";

export interface FixtureProvenance {
  source: string;
  generatedAt: string;
  notes: string;
}

export interface OverviewPayload {
  mocked: boolean;
  sourceMode?: SourceMode;
  controlPlane: string;
  summary: string;
  readiness: Status;
  freshness: {
    status: Status;
    lastUpdated: string;
    oldestSourceAgeSeconds: number;
  };
  counts: {
    activeRounds: number;
    blockedRounds: number;
    failedRounds: number;
    pendingReviews: number;
    unreadMessages: number;
  };
  sourceReadiness: Array<{ source: string; status: Status; freshnessSeconds: number }>;
  attentionTarget: { label: string; roundId: string | null; reason: string };
  recentActivity: ActivityEvent[];
}

export interface ActivityEvent {
  id: string;
  timestamp: string;
  severity: Severity;
  summary: string;
  roundId: string | null;
}

export interface RoundSummary {
  id: string;
  goal: string;
  state: Status;
  phase: string;
  owner: string;
  agents: string[];
  branchEvidence: { branch: string | null; headSha: string | null; status: string };
  validation: { state: Status; summary: string };
  finalReview: { state: Status; summary: string };
  blockers: string[];
  startedAt: string | null;
  updatedAt: string;
  latestEvent: string;
  source?: string;
  sourceMode?: SourceMode;
}

export interface RoundDetail {
  id: string;
  decisions: string[];
  timeline: Array<{ id: string; timestamp: string; actor: string; kind: string; summary: string }>;
  participants: Array<{ agent: string; role: string; status: string }>;
  validationOutput: { state: Status; commands: string[]; summary: string };
  artifacts: Array<{ label: string; path: string; kind: string }>;
  runnerOutput: string;
  relatedMessages: string[];
  rawPayloadRef: string;
  sourceMode?: SourceMode;
}

export interface InboxMessage {
  id: string;
  group: string;
  source: string;
  severity: Severity;
  timestamp: string;
  roundId: string | null;
  title: string;
  context: string;
  readOnly: boolean;
  sourceMode?: SourceMode;
}

export type SourceMode = "live" | "fixture";

export interface SourceHealth {
  name: string;
  source: string;
  kind: string;
  status: Status;
  detail: string;
  lastSeen: string | null;
  lastSuccessfulUpdate: string | null;
  freshnessSeconds: number | null;
  stale: boolean;
  sourceMode: SourceMode;
  fallback: boolean;
  error: string | null;
}

export interface ConnectionState {
  status: Status;
  transport: "sse" | "fixture" | "websocket" | "polling";
  lastEventId: string | null;
  lastHeartbeatAt: string | null;
  reconnect: {
    supported: boolean;
    maxBackoffSeconds: number;
    resumeParam?: string;
  };
}

export interface RuntimePayload {
  sources: Array<SourceHealth | { name: string; kind: string; status: Status; detail: string; lastSeen: string | null }>;
  previewService: {
    name: string;
    port: number;
    healthPath: string;
    fixtureOnly: boolean;
    liveReadsAllowed: boolean;
    mutationsAllowed: boolean;
    sourceMode?: SourceMode;
    streamPath?: string;
    snapshotPath?: string;
  };
}

export interface DiagnosticsPayload {
  schemaVersion: string;
  sourceMode?: SourceMode;
  generatedAt?: string;
  sourceErrors: Array<{ source: string; severity: Severity; message: string; observedAt: string }>;
  sourceHealth?: SourceHealth[];
  rawPayloads: Record<string, unknown>;
}

export interface PreviewFixtures {
  schemaVersion: string;
  sourceMode?: SourceMode;
  mocked: boolean;
  generatedAt?: string;
  cursor?: string;
  sources?: SourceHealth[];
  sourceHealth?: SourceHealth[];
  connection?: ConnectionState;
  fixtureProvenance: FixtureProvenance;
  overview: OverviewPayload;
  rounds: RoundSummary[];
  roundDetails: Record<string, RoundDetail>;
  inbox: InboxMessage[];
  runtime: RuntimePayload;
  diagnostics: DiagnosticsPayload;
}

export interface PreviewData extends PreviewFixtures {
  loadedAt: string;
}

export interface LiveSnapshot extends Omit<PreviewFixtures, "fixtureProvenance"> {
  schemaVersion: "new-ui-evaluation.live.v1";
  sourceMode: "live";
  mocked: false;
  generatedAt: string;
  cursor: string;
  sources: SourceHealth[];
  sourceHealth: SourceHealth[];
  connection: ConnectionState;
}

export interface LiveEvent {
  schemaVersion: "new-ui-evaluation.event.v1";
  type:
    | "heartbeat"
    | "snapshot_ready"
    | "source_status"
    | "round_updated"
    | "timeline_entry"
    | "inbox_item"
    | "runtime_health"
    | "diagnostic"
    | "stale"
    | "fallback"
    | "fatal";
  id: string;
  eventId: string;
  entityId: string | null;
  source: string;
  timestamp: string;
  version: string;
  cursor: string;
  payload: Record<string, unknown>;
  sourceStatus?: Status;
  stale: boolean;
  error?: string | null;
}
