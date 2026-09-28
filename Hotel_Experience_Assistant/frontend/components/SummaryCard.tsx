import type { Card } from "@/lib/websocket";

function humanize(name: string) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(key: string, value: unknown) {
  if (key.endsWith("_paise") && typeof value === "number") {
    return `₹${(value / 100).toLocaleString("en-IN")}`;
  }
  return String(value);
}

export function SummaryCard({ card }: { card: Card }) {
  return (
    <div data-testid="card" className="w-full max-w-xl rounded-lg border border-gray-300 p-4 shadow-sm">
      <h3 className="font-semibold mb-2">{humanize(card.tool)}</h3>
      <dl className="text-sm space-y-1">
        {Object.entries(card.data).map(([key, value]) => (
          <div key={key} className="flex justify-between gap-4">
            <dt className="text-gray-500">{humanize(key)}</dt>
            <dd>{formatValue(key, value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
