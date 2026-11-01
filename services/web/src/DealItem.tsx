import { airlineDisplayName } from "./airlines";
import { formatDuration, placeLabel, secondaryAirport, type Place } from "./format";
import type { Deal } from "./types";

// Deals cached before the added fields existed only have `destination` (a code), so
// every added field may be missing and the label falls back to that code.
export function DealItem({ deal }: { deal: Deal }) {
  const from: Place = {
    code: deal.origin,
    city: deal.origin_city,
    countryCode: deal.origin_country_code,
    airportName: deal.origin_airport_name,
  };
  const to: Place = {
    code: deal.destination,
    city: deal.destination_city,
    countryCode: deal.destination_country_code,
    airportName: deal.destination_airport_name,
  };
  const fromLabel = placeLabel(from);
  const fromSecondary = secondaryAirport(from);
  const toSecondary = secondaryAirport(to);

  return (
    <li>
      <strong>
        {fromLabel && `${fromLabel} → `}
        {placeLabel(to)}
      </strong>
      {(fromSecondary || toSecondary) && (
        <small className="airport">
          {" "}
          {[fromSecondary, toSecondary].filter(Boolean).join(" → ")}
        </small>
      )}{" "}
      · {deal.departure_date} · {deal.price} {deal.currency} ·{" "}
      {airlineDisplayName(deal.airline)}
      {deal.total_duration_minutes ? ` · ${formatDuration(deal.total_duration_minutes)}` : ""}
    </li>
  );
}
