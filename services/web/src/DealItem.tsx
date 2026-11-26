import { useState } from "react";
import {
  countryName,
  formatDay,
  formatDuration,
  formatPrice,
  placeLabel,
  secondaryAirport,
  type Place,
} from "./format";
import type { Deal } from "./types";

// "Rome, Italy" for the title; the full place label when the city is unknown.
function title(to: Place): string {
  if (to.city && to.countryCode) return `${to.city}, ${countryName(to.countryCode)}`;
  return placeLabel(to);
}

// The photo of a destination lives in public/destinations/<CODE>.webp. Without
// one (or if it fails to load) the card keeps its gradient.
function Photo({ code, name }: { code: string; name: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="deal-photo">
      {!failed && (
        <img
          src={`/destinations/${code}.webp`}
          alt={`View of ${name}`}
          loading="lazy"
          width={800}
          height={500}
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}

interface Props {
  deal: Deal;
  // Fills the search form with this deal and runs the search.
  onSeeFlights?: (deal: Deal) => void;
}

// Deals cached before the added fields existed only have `destination` (a code), so
// every added field may be missing and the label falls back to that code.
// A deal carries no booking link on purpose: its price is a cached one.
export function DealItem({ deal, onSeeFlights }: Props) {
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
  const name = title(to);
  // "12 Jan – 19 Jan" for a round trip, "12 Jan" for a one-way deal.
  const dates = deal.return_date
    ? `${formatDay(deal.departure_date)} – ${formatDay(deal.return_date)}`
    : formatDay(deal.departure_date);

  return (
    <li className="deal-card">
      <Photo code={deal.destination} name={name} />
      <div className="deal-body">
        <strong className="deal-title">{name}</strong>
        {fromLabel && (
          <small className="deal-route">
            {fromLabel} → {placeLabel(to)}
            {(fromSecondary || toSecondary) && (
              <small className="airport">
                {" "}
                {[fromSecondary, toSecondary].filter(Boolean).join(" → ")}
              </small>
            )}
          </small>
        )}
        <span className="deal-price">
          <small>from</small> {formatPrice(deal.price, deal.currency)}
          <small className="deal-kind">{deal.return_date ? "· round trip" : "· one way"}</small>
        </span>
        <span className="deal-meta">
          {dates} · {deal.airline}
          {deal.total_duration_minutes ? ` · ${formatDuration(deal.total_duration_minutes)}` : ""}
        </span>
        {onSeeFlights && deal.origin && (
          <button
            type="button"
            className="deal-btn"
            aria-label={`See flights to ${name}`}
            onClick={() => onSeeFlights(deal)}
          >
            See flights
          </button>
        )}
      </div>
    </li>
  );
}
