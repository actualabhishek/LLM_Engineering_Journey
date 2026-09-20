import type { StatsSummary } from "@/lib/stats";

interface Tile {
  label: string;
  value: number;
  accent: string;
}

export function StatsStrip({ stats }: { stats: StatsSummary }) {
  const tiles: Tile[] = [
    {
      label: "Open Change Requests",
      value: stats.openChangeRequests,
      accent: "var(--color-accent-blue)",
    },
    {
      label: "Active Incidents (P1/P2)",
      value: stats.activeIncidents,
      accent: "var(--color-danger-red)",
    },
    { label: "SLA at Risk", value: stats.slaAtRisk, accent: "var(--color-warning-amber)" },
    {
      label: "Deployments This Week",
      value: stats.deploymentsThisWeek,
      accent: "var(--color-success-green)",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 px-6 pt-6 md:grid-cols-4">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="rounded-xl border border-line bg-surface p-4"
        >
          <div
            className="mb-2 h-1 w-8 rounded-full"
            style={{ backgroundColor: tile.accent }}
          />
          <p className="text-2xl font-semibold text-ink">
            {tile.value}
          </p>
          <p className="text-xs font-medium text-muted">{tile.label}</p>
        </div>
      ))}
    </div>
  );
}
