import type {
  DiagnosticsPayload,
  InboxMessage,
  OverviewPayload,
  PreviewData,
  PreviewFixtures,
  RoundDetail,
  RoundSummary,
  RuntimePayload
} from "./types";

const headers = { Accept: "application/json" };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "GET", headers });
  if (!response.ok) {
    throw new Error(`Preview fixture request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function loadPreviewData(): Promise<PreviewData> {
  const [fixtures, overview, rounds, inbox, runtime, diagnostics] = await Promise.all([
    getJson<PreviewFixtures>("/api/fixtures"),
    getJson<OverviewPayload>("/api/overview"),
    getJson<RoundSummary[]>("/api/rounds"),
    getJson<InboxMessage[]>("/api/inbox"),
    getJson<RuntimePayload>("/api/runtime"),
    getJson<DiagnosticsPayload>("/api/diagnostics")
  ]);

  return {
    ...fixtures,
    overview,
    rounds,
    inbox,
    runtime,
    diagnostics,
    loadedAt: new Date().toISOString()
  };
}

export async function loadRoundDetail(roundId: string): Promise<RoundDetail | null> {
  const response = await fetch(`/api/rounds/${encodeURIComponent(roundId)}`, {
    method: "GET",
    headers
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Preview round fixture request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as RoundDetail;
}
