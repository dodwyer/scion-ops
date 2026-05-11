import { AlertTriangle, CheckCircle2, CircleDot, Database, GitBranch, Inbox, RefreshCcw, Server, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { applyLiveEvent, fixtureModeRequested, loadOperatorData, markOperatorDataStale, openLiveEventStream } from "./api";
import type { DiagnosticsPayload, InboxMessage, LiveConnection, LiveEvent, OperatorData, RoundDetail, RoundSummary, SourceHealth, Status } from "./types";

type View = "overview" | "rounds" | "detail" | "inbox" | "runtime" | "diagnostics";

const views: Array<{ id: View; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "rounds", label: "Rounds" },
  { id: "detail", label: "Round Detail" },
  { id: "inbox", label: "Inbox" },
  { id: "runtime", label: "Runtime" },
  { id: "diagnostics", label: "Diagnostics" }
];

const statusClass: Record<string, string> = {
  healthy: "good",
  live: "good",
  passed: "good",
  accepted: "good",
  completed: "good",
  active: "info",
  running: "info",
  reconnecting: "info",
  fixture: "fixture",
  fallback: "fixture",
  waiting: "warn",
  stale: "warn",
  degraded: "warn",
  blocked: "bad",
  failed: "bad",
  critical: "bad",
  empty: "muted",
  "not-started": "muted"
};

export function App() {
  const fixtureMode = useMemo(() => fixtureModeRequested(), []);
  const [data, setData] = useState<OperatorData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>("overview");
  const [selectedRoundId, setSelectedRoundId] = useState<string>("");
  const [roundFilter, setRoundFilter] = useState("all");
  const reconnectTimer = useRef<number | null>(null);
  const reconnectAttempt = useRef(0);
  const eventSource = useRef<EventSource | null>(null);

  async function refresh() {
    setLoadError(null);
    try {
      const operatorData = await loadOperatorData({ fixtureMode });
      setData(operatorData);
      setSelectedRoundId((current) => (operatorData.rounds.some((round) => round.id === current) ? current : operatorData.rounds[0]?.id ?? ""));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Unable to load operator data");
    }
  }

  useEffect(() => {
    void refresh();
    return () => {
      eventSource.current?.close();
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!data || data.sourceMode !== "live") {
      return;
    }
    const timer = window.setInterval(() => setData((current) => (current ? markOperatorDataStale(current) : current)), 5_000);
    return () => window.clearInterval(timer);
  }, [data?.sourceMode]);

  useEffect(() => {
    if (!data || data.sourceMode !== "live") {
      eventSource.current?.close();
      eventSource.current = null;
      return;
    }
    const streamPath = data.runtime.liveService.streamPath ?? "/api/events";
    connectStream(streamPath, data.cursor);
    return () => {
      eventSource.current?.close();
      eventSource.current = null;
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
    };
  }, [data?.sourceMode, data?.runtime.liveService.streamPath]);

  function connectStream(streamPath: string, cursor: string) {
    eventSource.current?.close();
    const maxReconnectBackoff = data?.connection.reconnect.maxBackoffSeconds || 30;
    const handleStreamError = (message = "SSE stream interrupted") => {
      eventSource.current?.close();
      const attempt = Math.min(reconnectAttempt.current + 1, 6);
      reconnectAttempt.current = attempt;
      const delaySeconds = Math.min(maxReconnectBackoff, 2 ** attempt);
      setData((current) => current && current.sourceMode === "live" ? withConnection(current, { status: "reconnecting", error: message, attempt, nextDelaySeconds: delaySeconds }) : current);
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
      reconnectTimer.current = window.setTimeout(() => {
        setData((current) => {
          if (!current || current.sourceMode !== "live") return current;
          connectStream(current.runtime.liveService.streamPath ?? streamPath, current.cursor);
          return current;
        });
      }, delaySeconds * 1_000);
    };
    try {
      eventSource.current = openLiveEventStream({
        streamPath,
        cursor,
        onOpen: () => {
          reconnectAttempt.current = 0;
          setData((current) => current && current.sourceMode === "live" ? withConnection(current, { status: "live", error: null }) : current);
        },
        onEvent: (event: LiveEvent) => {
          reconnectAttempt.current = 0;
          setData((current) => current ? applyLiveEvent(current, event) : current);
        },
        onError: () => handleStreamError()
      });
    } catch (error) {
      handleStreamError(error instanceof Error ? error.message : "SSE stream unavailable");
    }
  }

  const filteredRounds = useMemo(() => {
    if (!data || roundFilter === "all") {
      return data?.rounds ?? [];
    }
    return data.rounds.filter((round) => round.state === roundFilter || round.phase === roundFilter);
  }, [data, roundFilter]);

  if (loadError) {
    return (
      <main className="shell">
        <Header loadedAt={null} connection={null} onRefresh={refresh} />
        <section className="notice error">
          <AlertTriangle size={18} />
          <span>{loadError}</span>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="shell">
        <Header loadedAt={null} connection={null} onRefresh={refresh} />
        <section className="loading">Loading live operator snapshot...</section>
      </main>
    );
  }

  const roundDetail = selectedRoundId ? data.roundDetails[selectedRoundId] ?? null : null;

  return (
    <main className="shell">
      <Header loadedAt={data.loadedAt} connection={data.connection} onRefresh={refresh} />
      <ConnectionStrip data={data} />
      <nav className="tabs" aria-label="Operator views">
        {views.map((item) => (
          <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>
      {view === "overview" && <Overview data={data} onOpenRound={(id) => { setSelectedRoundId(id); setView("detail"); }} />}
      {view === "rounds" && (
        <RoundsView
          rounds={filteredRounds}
          allRounds={data.rounds}
          filter={roundFilter}
          onFilter={setRoundFilter}
          onSelect={(id) => {
            setSelectedRoundId(id);
            setView("detail");
          }}
        />
      )}
      {view === "detail" && <RoundDetailView round={data.rounds.find((item) => item.id === selectedRoundId) ?? null} detail={roundDetail} diagnostics={data.diagnostics} />}
      {view === "inbox" && <InboxView messages={data.inbox} onOpenRound={(id) => { setSelectedRoundId(id); setView("detail"); }} />}
      {view === "runtime" && <RuntimeView data={data} />}
      {view === "diagnostics" && <DiagnosticsView diagnostics={data.diagnostics} sourceHealth={data.sourceHealth} />}
    </main>
  );
}

function withConnection(data: OperatorData, update: { status: LiveConnection["status"]; error?: string | null; attempt?: number; nextDelaySeconds?: number }): OperatorData {
  return {
    ...data,
    connection: {
      ...data.connection,
      status: update.status,
      error: update.error,
      reconnect: {
        ...data.connection.reconnect,
        attempt: update.attempt ?? data.connection.reconnect.attempt,
        nextDelaySeconds: update.nextDelaySeconds
      }
    }
  };
}

function Header({ loadedAt, connection, onRefresh }: { loadedAt: string | null; connection: LiveConnection | null; onRefresh: () => void }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Scion Ops</p>
        <h1>Operator Console</h1>
      </div>
      <div className="topbar-actions">
        <span className="timestamp">{loadedAt ? `Snapshot loaded ${formatTime(loadedAt)}` : "Snapshot loading"}</span>
        {connection && <Badge value={connection.status} />}
        <button className="icon-button" onClick={onRefresh} aria-label="Refresh operator snapshot" title="Refresh operator snapshot">
          <RefreshCcw size={18} />
        </button>
      </div>
    </header>
  );
}

function ConnectionStrip({ data }: { data: OperatorData }) {
  const Icon = data.connection.status === "failed" || data.connection.status === "stale" ? WifiOff : Wifi;
  const staleSources = data.sourceHealth.filter((source) => source.stale || source.status === "stale" || source.status === "failed" || source.error);
  const message = data.sourceMode === "fixture"
    ? data.fixtureProvenance?.notes ?? "Explicit fixture fallback is active."
    : `${data.connection.transport.toUpperCase()} updates via ${data.runtime.liveService.streamPath ?? "/api/events"}`;
  return (
    <section className={`connection-strip ${statusClass[data.connection.status] ?? "muted"}`}>
      <Icon size={18} />
      <span>{message}</span>
      <Badge value={data.sourceMode === "fixture" ? "fallback" : data.connection.status} />
      {data.connection.reconnect.nextDelaySeconds && <small>Retry in {data.connection.reconnect.nextDelaySeconds}s</small>}
      {staleSources.length > 0 && <small>{staleSources.map((source) => source.name).join(", ")} need attention</small>}
    </section>
  );
}

function Overview({ data, onOpenRound }: { data: OperatorData; onOpenRound: (roundId: string) => void }) {
  const counts = data.overview.counts;
  return (
    <section className="view-grid">
      <div className="metric-row">
        <Metric label="Readiness" value={data.overview.readiness} status={data.overview.readiness} />
        <Metric label="Active rounds" value={counts.activeRounds.toString()} status="active" />
        <Metric label="Blocked" value={counts.blockedRounds.toString()} status="blocked" />
        <Metric label="Freshness" value={data.overview.freshness.status} status={data.overview.freshness.status} />
      </div>
      <section className="panel attention">
        <div>
          <p className="eyebrow">Next inspection</p>
          <h2>{data.overview.attentionTarget.label}</h2>
          <p>{data.overview.attentionTarget.reason}</p>
        </div>
        {data.overview.attentionTarget.roundId && (
          <button onClick={() => onOpenRound(data.overview.attentionTarget.roundId as string)}>Open round</button>
        )}
      </section>
      <section className="two-column">
        <SourceHealthPanel sources={data.sourceHealth} />
        <div className="panel">
          <PanelTitle icon={<CircleDot size={18} />} title="Recent activity" />
          <div className="activity-list">
            {data.overview.recentActivity.map((event) => (
              <button key={event.id} className="activity" onClick={() => event.roundId && onOpenRound(event.roundId)} disabled={!event.roundId}>
                <Badge value={event.severity} />
                <span>{event.summary}</span>
                <small>{formatTime(event.timestamp)}</small>
              </button>
            ))}
          </div>
        </div>
      </section>
    </section>
  );
}

function SourceHealthPanel({ sources }: { sources: SourceHealth[] }) {
  return (
    <div className="panel">
      <PanelTitle icon={<Server size={18} />} title="Source readiness" />
      <div className="source-list">
        {sources.map((source) => (
          <div key={source.name} className={`source-row ${source.stale ? "is-stale" : ""}`}>
            <span>
              <strong>{source.name}</strong>
              <small>{source.kind}</small>
            </span>
            <Badge value={source.status} />
            <small>{source.freshnessSeconds ?? "unknown"}s</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoundsView({ rounds, allRounds, filter, onFilter, onSelect }: { rounds: RoundSummary[]; allRounds: RoundSummary[]; filter: string; onFilter: (value: string) => void; onSelect: (id: string) => void }) {
  const filters = ["all", ...Array.from(new Set(allRounds.flatMap((round) => [round.state, round.phase])))];
  return (
    <section className="panel">
      <div className="panel-header">
        <PanelTitle icon={<GitBranch size={18} />} title="Round comparison" />
        <select value={filter} onChange={(event) => onFilter(event.target.value)} aria-label="Filter rounds">
          {filters.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Round</th><th>State</th><th>Phase</th><th>Validation</th><th>Final review</th><th>Branch</th><th>Latest event</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((round) => (
              <tr key={round.id} onClick={() => onSelect(round.id)}>
                <td><strong>{round.id}</strong><span>{round.goal}</span></td>
                <td><Badge value={round.state} /></td>
                <td>{round.phase}</td>
                <td><Badge value={round.validation.state} /></td>
                <td><Badge value={round.finalReview.state} /></td>
                <td>{round.branchEvidence.branch ?? "none"} <small>{round.branchEvidence.status}</small></td>
                <td>{round.latestEvent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RoundDetailView({ round, detail, diagnostics }: { round: RoundSummary | null; detail: RoundDetail | null; diagnostics: DiagnosticsPayload }) {
  if (!round) return <section className="notice">No round selected.</section>;
  const rawPayload = detail?.rawPayloadRef ? diagnostics.rawPayloads[detail.rawPayloadRef] : null;
  return (
    <section className="view-grid">
      <section className="panel">
        <div className="detail-heading">
          <div><p className="eyebrow">{round.phase}</p><h2>{round.goal}</h2><p>{round.id}</p></div>
          <Badge value={round.state} />
        </div>
        <div className="detail-grid">
          <Metric label="Validation" value={round.validation.state} status={round.validation.state} />
          <Metric label="Final review" value={round.finalReview.state} status={round.finalReview.state} />
          <Metric label="Branch evidence" value={round.branchEvidence.status} status={round.branchEvidence.status === "present" ? "healthy" : "blocked"} />
        </div>
        {round.blockers.length > 0 && <p className="blocker">Blockers: {round.blockers.join(", ")}</p>}
      </section>
      {detail ? (
        <section className="two-column">
          <div className="panel">
            <PanelTitle icon={<CircleDot size={18} />} title="Timeline" />
            <div className="timeline">
              {detail.timeline.map((item) => <div key={item.id}><small>{formatTime(item.timestamp)} · {item.actor}</small><strong>{item.kind}</strong><span>{item.summary}</span></div>)}
            </div>
          </div>
          <div className="panel">
            <PanelTitle icon={<CheckCircle2 size={18} />} title="Evidence" />
            <h3>Decisions</h3><ul>{detail.decisions.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>Artifacts</h3><ul>{detail.artifacts.map((item) => <li key={item.label}>{item.label}: {item.path}</li>)}</ul>
            <h3>Runner output</h3><pre>{detail.runnerOutput}</pre>
          </div>
        </section>
      ) : <section className="notice">No live detail has been reported for the selected round.</section>}
      {rawPayload != null && <details className="panel raw"><summary>Raw payload</summary><pre>{JSON.stringify(rawPayload, null, 2)}</pre></details>}
    </section>
  );
}

function InboxView({ messages, onOpenRound }: { messages: InboxMessage[]; onOpenRound: (roundId: string) => void }) {
  const grouped = messages.reduce<Record<string, InboxMessage[]>>((groups, message) => ({ ...groups, [message.group]: [...(groups[message.group] ?? []), message] }), {});
  return (
    <section className="panel">
      <PanelTitle icon={<Inbox size={18} />} title="Read-only inbox" />
      <div className="message-groups">
        {Object.entries(grouped).map(([group, groupMessages]) => (
          <div key={group} className="message-group">
            <h2>{group}</h2>
            {groupMessages.map((message) => (
              <button key={message.id} className="message" onClick={() => message.roundId && onOpenRound(message.roundId)} disabled={!message.roundId}>
                <Badge value={message.severity} />
                <span><strong>{message.title}</strong>{message.context}</span>
                <small>{formatTime(message.timestamp)}</small>
              </button>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function RuntimeView({ data }: { data: OperatorData }) {
  return (
    <section className="two-column">
      <div className="panel">
        <PanelTitle icon={<Server size={18} />} title="Runtime and sources" />
        <div className="source-list">
          {data.runtime.sources.map((source) => (
            <div key={source.name} className={`source-row wide ${source.stale ? "is-stale" : ""}`}>
              <span><strong>{source.name}</strong><small>{source.kind}</small></span>
              <Badge value={source.status} />
              <p>{source.error ?? source.detail}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <PanelTitle icon={<ShieldCheck size={18} />} title="Live safeguards" />
        <dl className="facts">
          <div><dt>Service</dt><dd>{data.runtime.liveService.name}</dd></div>
          <div><dt>Snapshot</dt><dd>{data.runtime.liveService.snapshotPath ?? "/api/snapshot"}</dd></div>
          <div><dt>Stream</dt><dd>{data.runtime.liveService.streamPath ?? "disabled"}</dd></div>
          <div><dt>Local fixture fallback</dt><dd>{String(data.runtime.liveService.fixtureOnly)}</dd></div>
          <div><dt>Live reads</dt><dd>{String(data.runtime.liveService.liveReadsAllowed)}</dd></div>
          <div><dt>Mutations</dt><dd>{String(data.runtime.liveService.mutationsAllowed)}</dd></div>
        </dl>
      </div>
    </section>
  );
}

function DiagnosticsView({ diagnostics, sourceHealth }: { diagnostics: DiagnosticsPayload; sourceHealth: SourceHealth[] }) {
  return (
    <section className="view-grid">
      <section className="panel">
        <PanelTitle icon={<Database size={18} />} title="Diagnostics" />
        <p>Schema: {diagnostics.schemaVersion}</p>
        <div className="source-list">
          {diagnostics.sourceErrors.map((error) => (
            <div key={`${error.source}-${error.observedAt}`} className="source-row wide">
              <span>{error.source}</span><Badge value={error.severity} /><p>{error.message}</p>
            </div>
          ))}
          {diagnostics.sourceErrors.length === 0 && sourceHealth.map((source) => (
            <div key={source.name} className="source-row wide"><span>{source.name}</span><Badge value={source.status} /><p>{source.detail}</p></div>
          ))}
        </div>
      </section>
      <details className="panel raw"><summary>Raw payload index</summary><pre>{JSON.stringify(diagnostics.rawPayloads, null, 2)}</pre></details>
    </section>
  );
}

function Metric({ label, value, status }: { label: string; value: string; status: Status | string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><Badge value={status} /></div>;
}

function PanelTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <div className="panel-title">{icon}<h2>{title}</h2></div>;
}

function Badge({ value }: { value: string }) {
  return <span className={`badge ${statusClass[value] ?? "muted"}`}>{value}</span>;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
