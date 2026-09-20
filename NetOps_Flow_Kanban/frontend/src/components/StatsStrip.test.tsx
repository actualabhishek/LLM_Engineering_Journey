import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatsStrip } from "./StatsStrip";

describe("StatsStrip", () => {
  it("renders all four tiles with their computed values", () => {
    render(
      <StatsStrip
        stats={{
          openChangeRequests: 3,
          activeIncidents: 2,
          slaAtRisk: 1,
          deploymentsThisWeek: 4,
        }}
      />
    );

    expect(screen.getByText("Open Change Requests")).toBeInTheDocument();
    expect(screen.getByText("Active Incidents (P1/P2)")).toBeInTheDocument();
    expect(screen.getByText("SLA at Risk")).toBeInTheDocument();
    expect(screen.getByText("Deployments This Week")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});
