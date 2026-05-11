import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import fixtures from "../../fixtures/preview-fixtures.json";
import { App } from "../App";
import type { PreviewFixtures } from "../types";

const typedFixtures = fixtures as PreviewFixtures;

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("preview fixture contract", () => {
  it("keeps the UI data mocked and read-only", () => {
    expect(typedFixtures.mocked).toBe(true);
    expect(typedFixtures.overview.mocked).toBe(true);
    expect(typedFixtures.runtime.previewService.fixtureOnly).toBe(true);
    expect(typedFixtures.runtime.previewService.liveReadsAllowed).toBe(false);
    expect(typedFixtures.runtime.previewService.mutationsAllowed).toBe(false);
    expect(typedFixtures.rounds.map((round) => round.state)).toEqual(
      expect.arrayContaining(["blocked", "active", "failed", "completed", "empty"])
    );
  });

  it("renders the operational overview from fixture endpoints", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = input.toString();
      if (path === "/api/fixtures") return Promise.resolve(jsonResponse(typedFixtures));
      if (path === "/api/overview") return Promise.resolve(jsonResponse(typedFixtures.overview));
      if (path === "/api/rounds") return Promise.resolve(jsonResponse(typedFixtures.rounds));
      if (path === "/api/inbox") return Promise.resolve(jsonResponse(typedFixtures.inbox));
      if (path === "/api/runtime") return Promise.resolve(jsonResponse(typedFixtures.runtime));
      if (path === "/api/diagnostics") return Promise.resolve(jsonResponse(typedFixtures.diagnostics));
      if (path.startsWith("/api/rounds/")) {
        return Promise.resolve(jsonResponse(typedFixtures.roundDetails["round-20260511t091500z-117a"]));
      }
      return Promise.resolve(jsonResponse({ error: "not found" }, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => expect(screen.getByText("Blocked final review")).toBeInTheDocument());
    expect(screen.getByText("Preview Console")).toBeInTheDocument();
    expect(screen.getByText(/records are not live scion-ops state/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/overview", expect.objectContaining({ method: "GET" }));
  });
});
