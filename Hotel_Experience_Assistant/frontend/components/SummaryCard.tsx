import type { Card } from "@/lib/websocket";

const TITLES: Record<string, string> = {
  create_booking: "Booking Confirmed",
  modify_booking: "Booking Updated",
  cancel_booking: "Booking Cancelled",
  enroll_loyalty: "Loyalty Enrollment",
  redeem_points: "Points Redeemed",
  check_in: "Check-In Confirmed",
};

const FIELD_LABELS: Record<string, string> = {
  total_price_paise: "Total",
  num_guests: "Guests",
};

// Redundant once a friendlier field is already shown alongside it (e.g. room_type_name).
const HIDDEN_FIELDS = new Set(["room_type_code"]);

function humanize(name: string) {
  return FIELD_LABELS[name] ?? name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(key: string, value: unknown) {
  if (key.endsWith("_paise") && typeof value === "number") {
    return `₹${(value / 100).toLocaleString("en-IN")}`;
  }
  return String(value);
}

export function SummaryCard({ card }: { card: Card }) {
  return (
    <div
      data-testid="card"
      className="w-full max-w-xl bg-parchment text-velvet-deep border-t-4 border-gold p-5"
    >
      <h3 className="font-serif text-lg font-semibold mb-3">
        {TITLES[card.tool] ?? humanize(card.tool)}
      </h3>
      <dl className="text-sm space-y-1.5">
        {Object.entries(card.data)
          .filter(([key, value]) => value !== null && value !== undefined && !HIDDEN_FIELDS.has(key))
          .map(([key, value]) => (
            <div key={key} className="flex justify-between gap-4">
              <dt className="text-velvet-deep/60">{humanize(key)}</dt>
              <dd className="font-medium">{formatValue(key, value)}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}
