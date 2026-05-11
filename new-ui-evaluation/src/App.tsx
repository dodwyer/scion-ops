import { AlertTriangle, CheckCircle2, CircleDot, Database, GitBranch, Inbox, RefreshCcw, Server, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { loadPreviewData, loadRoundDetail } from "./api";
import type { DiagnosticsPayload, InboxMessage, PreviewData, RoundDetail, RoundSummary, Status } from "./types";

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
  passed: "good",
  accepted: "good",
  completed: "good",
  active: "info",
  running: "info",
  mocked: "mocked",
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
  const [data, setData] = useState<PreviewData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>("overview");
  const [selectedRoundId, setSelectedRoundId] = useState<string>("round-20260511t091500z-117a");
  const [roundDetail, setRoundDetail] = useState<RoundDetail | null>(null);
  const [roundFilter, setRoundFilter] = useState("all");

  async function refresh() {
    setLoadError(null);
    try {
      const previewData = await loadPreviewData();
      setData(previewData);
      if (!previewData.rounds.some((round) => round.id === selectedRoundId)) {
        setSelectedRoundId(previewData.rounds[0]?.id ?? "");
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Unable to load preview fixtures");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!selectedRoundId) {
      setRoundDetail(null);
      return;
    }
    void loadRoundDetail(selectedRoundId).then(setRoundDetail).catch(() => setRoundDetail(null));
  }, [selectedRoundId]);

  const filteredRounds = useMemo(() => {
    if (!data || roundFilter === "all") {
      return data?.rounds ?? [];
    }
    return data.rounds.filter((round) => round.state === roundFilter || round.phase === roundFilter);
  }, [data, roundFilter]);

  if (loadError) {
    return (
      <main className="shell">
        <Header loadedAt={null} onRefresh={refresh} />
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
        <Header loadedAt={null} onRefresh={refresh} />
        <section className="loading">Loading preview fixtures...</section>
      </main>
    );
  }

  return (
    <main className="shell">
      <Header loadedAt={data.loadedAt} onRefresh={refresh} />
      <section className="fixture-strip">
        <ShieldCheck size={18} />
        <span>{data.fixtureProvenance.notes}</span>
      </section>
      <nav className="tabs" aria-label="Preview views">
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
      {view === "diagnostics" && <DiagnosticsView diagnostics={data.diagnostics} />}
    </main>
  );
}

function Header({ loadedAt, onRefresh }: { loadedAt: string | null; onRefresh: () => void }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Scion Ops</p>
        <h1>Preview Console</h1>
      </div>
      <div className="topbar-actions">
        <span className="timestamp">{loadedAt ? `Fixture loaded ${formatTime(loadedAt)}` : "Fixture loading"}</span>
        <button className="icon-button" onClick={onRefresh} aria-label="Refresh local preview fixtures" title="Refresh local preview fixtures">
          <RefreshCcw size={18} />
        </button>
      </div>
    </header>
  );
}

function Overview({ data, onOpenRound }: { data: PreviewData; onOpenRound: (roundId: string) => void }) {
  const counts = data.overview.counts;
  return (
    <section className="view-grid">
      <div className="metric-row">
        <Metric label="Readiness" value={data.overview.readiness} status={data.overview.readiness} />
        <Metric label="Active rounds" value={counts.activeRounds.toString()} status="active" />
        <Metric label="Blocked" value={counts.blockedRounds.toString()} status="blocked" />
        <Metric label="Pending review" value={counts.pendingReviews.toString()} status="waiting" />
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
        <div className="panel">
          <PanelTitle icon={<Server size={18} />} title="Source readiness" />
          <div className="source-list">
            {data.overview.sourceReadiness.map((source) => (
              <div key={source.source} className="source-row">
                <span>{source.source}</span>
                <Badge value={source.status} />
                <small>{source.freshnessSeconds}s</small>
              </div>
            ))}
          </div>
        </div>
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

function RoundsView({ rounds, allRounds, filter, onFilter, onSelect }: { rounds: RoundSummary[]; allRounds: RoundSummary[]; filter: string; onFilter: (value: string) => void; onSelect: (id: string) => void }) {
  const filters = ["all", ...Array.from(new Set(allRounds.flatMap((round) => [round.state, round.phase])))];
  return (
    <section className="panel">
      <div className="panel-header">
        <PanelTitle icon={<GitBranch size={18} />} title="Round comparison" />
        <select value={filter} onChange={(event) => onFilter(event.target.value)} aria-label="Filter rounds">
          {filters.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Round</th>
              <th>State</th>
              <th>Phase</th>
              <th>Validation</th>
              <th>Final review</th>
              <th>Branch</th>
              <th>Latest event</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((round) => (
              <tr key={round.id} onClick={() => onSelect(round.id)}>
                <td>
                  <strong>{round.id}</strong>
                  <span>{round.goal}</span>
                </td>
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
  if (!round) {
    return <section className="notice">No round selected.</section>;
  }
  const rawPayload = detail?.rawPayloadRef ? diagnostics.rawPayloads[detail.rawPayloadRef] : null;
  return (
    <section className="view-grid">
      <section className="panel">
        <div className="detail-heading">
          <div>
            <p className="eyebrow">{round.phase}</p>
            <h2>{round.goal}</h2>
            <p>{round.id}</p>
          </div>
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
              {detail.timeline.map((item) => (
                <div key={item.id}>
                  <small>{formatTime(item.timestamp)} · {item.actor}</small>
                  <strong>{item.kind}</strong>
                  <span>{item.summary}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="panel">
            <PanelTitle icon={<CheckCircle2 size={18} />} title="Evidence" />
            <h3>Decisions</h3>
            <ul>{detail.decisions.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>Artifacts</h3>
            <ul>{detail.artifacts.map((item) => <li key={item.label}>{item.label}: {item.path}</li>)}</ul>
            <h3>Runner output</h3>
            <pre>{detail.runnerOutput}</pre>
          </div>
        </section>
      ) : (
        <section className="notice">This fixture demonstrates an empty detail state for the selected round.</section>
      )}
      {rawPayload != null && (
        <details className="panel raw">
          <summary>Raw fixture payload</summary>
          <pre>{JSON.stringify(rawPayload, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

function InboxView({ messages, onOpenRound }: { messages: InboxMessage[]; onOpenRound: (roundId: string) => void }) {
  const grouped = messages.reduce<Record<string, InboxMessage[]>>((groups, message) => {
    groups[message.group] = [...(groups[message.group] ?? []), message];
    return groups;
  }, {});
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
                <span>
                  <strong>{message.title}</strong>
                  {message.context}
                </span>
                <small>{formatTime(message.timestamp)}</small>
              </button>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function RuntimeView({ data }: { data: PreviewData }) {
  return (
    <section className="two-column">
      <div className="panel">
        <PanelTitle icon={<Server size={18} />} title="Runtime and sources" />
        <div className="source-list">
          {data.runtime.sources.map((source) => (
            <div key={source.name} className="source-row wide">
              <span>
                <strong>{source.name}</strong>
                <small>{source.kind}</small>
              </span>
              <Badge value={source.status} />
              <p>{source.detail}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <PanelTitle icon={<ShieldCheck size={18} />} title="Preview safeguards" />
        <dl className="facts">
          <div><dt>Service</dt><dd>{data.runtime.previewService.name}</dd></div>
          <div><dt>Port</dt><dd>{data.runtime.previewService.port}</dd></div>
          <div><dt>Health</dt><dd>{data.runtime.previewService.healthPath}</dd></div>
          <div><dt>Fixture only</dt><dd>{String(data.runtime.previewService.fixtureOnly)}</dd></div>
          <div><dt>Live reads</dt><dd>{String(data.runtime.previewService.liveReadsAllowed)}</dd></div>
          <div><dt>Mutations</dt><dd>{String(data.runtime.previewService.mutationsAllowed)}</dd></div>
        </dl>
      </div>
    </section>
  );
}

function DiagnosticsView({ diagnostics }: { diagnostics: DiagnosticsPayload }) {
  return (
    <section className="view-grid">
      <section className="panel">
        <PanelTitle icon={<Database size={18} />} title="Diagnostics" />
        <p>Schema: {diagnostics.schemaVersion}</p>
        <div className="source-list">
          {diagnostics.sourceErrors.map((error) => (
            <div key={`${error.source}-${error.observedAt}`} className="source-row wide">
              <span>{error.source}</span>
              <Badge value={error.severity} />
              <p>{error.message}</p>
            </div>
          ))}
        </div>
      </section>
      <details className="panel raw">
        <summary>Raw payload index</summary>
        <pre>{JSON.stringify(diagnostics.rawPayloads, null, 2)}</pre>
      </details>
    </section>
  );
}

function Metric({ label, value, status }: { label: string; value: string; status: Status | string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <Badge value={status} />
    </div>
  );
}

function PanelTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function Badge({ value }: { value: string }) {
  return <span className={`badge ${statusClass[value] ?? "muted"}`}>{value}</span>;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
