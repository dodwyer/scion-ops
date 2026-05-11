export type Status =
  | "healthy"
  | "degraded"
  | "stale"
  | "mocked"
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
}

export interface RuntimePayload {
  sources: Array<{
    name: string;
    kind: string;
    status: Status;
    detail: string;
    lastSeen: string | null;
  }>;
  previewService: {
    name: string;
    port: number;
    healthPath: string;
    fixtureOnly: boolean;
    liveReadsAllowed: boolean;
    mutationsAllowed: boolean;
  };
}

export interface DiagnosticsPayload {
  schemaVersion: string;
  sourceErrors: Array<{ source: string; severity: Severity; message: string; observedAt: string }>;
  rawPayloads: Record<string, unknown>;
}

export interface PreviewFixtures {
  schemaVersion: string;
  mocked: true;
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
