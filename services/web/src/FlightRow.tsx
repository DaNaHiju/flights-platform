import { useId, useState } from "react";
import { AIRLINES, airlineUrl } from "./airlines";
import {
  dayDifference,
  formatDuration,
  formatPrice,
  localTime,
  minutesBetween,
} from "./format";
import { baggageInfo } from "./baggage";
import { airlinesOf, totalMinutes } from "./results";
import type { FlightOffer, Leg } from "./types";

// One direction of a trip. A one-way row has one; a round trip has two.
export interface Direction {
  label?: string;
  offer: FlightOffer;
}

interface Props {
  directions: Direction[];
  price: number;
  currency: string;
  deepLink?: string | null;
  // "Choose" button in a list; the row is then a step of the selection.
  onChoose?: () => void;
  // Small text over the price ("from") and under it (defaults to one way / round trip).
  pricePrefix?: string;
  caption?: string;
  // Review: start expanded and show Book / Go to. Lists never show them.
  review?: boolean;
  bookLabel?: string;
  // Travelers the price covers. Over 1, the price says "total for N travelers".
  travelers?: number;
}

const first = (offer: FlightOffer): Leg | undefined => offer.legs[0];
const last = (offer: FlightOffer): Leg | undefined => offer.legs[offer.legs.length - 1];

// "Rome (FCO)" / "FCO" / the airport name, whatever the leg has.
function layoverPlace(leg: Leg): string {
  const code = leg.arrival_airport_code;
  if (leg.arrival_city && code) return `${leg.arrival_city} (${code})`;
  return code || leg.arrival_airport;
}

// "Ben Gurion International Airport (TLV)"
function airportLabel(name: string, code?: string | null): string {
  return code ? `${name} (${code})` : name;
}

// Airports where the trip changes planes, in order: the arrival of every leg but the last.
function stopAirports(offer: FlightOffer): string[] {
  return offer.legs.slice(0, -1).map((leg) => leg.arrival_airport_code || leg.arrival_airport);
}

function stopsText(offer: FlightOffer): string {
  if (offer.stops === 0) return "Nonstop";
  const label = `${offer.stops} stop${offer.stops > 1 ? "s" : ""}`;
  const airports = stopAirports(offer);
  return airports.length > 0 ? `${label} · ${airports.join(", ")}` : label;
}

// Only when both codes are known; without them we cannot tell a change from missing data.
function changesAirport(arriving: Leg, departing: Leg): boolean {
  const from = arriving.arrival_airport_code;
  const to = departing.departure_airport_code;
  return !!from && !!to && from !== to;
}

// The layover crosses local midnight when the next flight leaves on a later
// calendar day than the previous one landed, both read as local dates.
function isOvernight(arriving: Leg, departing: Leg): boolean {
  return dayDifference(arriving.arrival_datetime, departing.departure_datetime) > 0;
}

// "1 checked bag · 23 kg", or an honest "not available" when the API did not say.
function BaggageBadge({ offer }: { offer: FlightOffer }) {
  const { kind, text } = baggageInfo(offer);
  return <span className={`fr-bag ${kind}`}>{text}</span>;
}

// Compact line: airlines, times with the stops in the middle, and stops text.
function Summary({ direction }: { direction: Direction }) {
  const { offer, label } = direction;
  const start = first(offer);
  const end = last(offer);
  const days = start && end ? dayDifference(start.departure_datetime, end.arrival_datetime) : 0;
  return (
    <span className="fr-line">
      <span className="fr-airlines">
        {label && <span className="fr-label">{label}</span>}
        {airlinesOf([offer]).join(", ")}
      </span>
      <span className="fr-times">
        {start && end && (
          <span className="fr-clock">
            {localTime(start.departure_datetime)} → {localTime(end.arrival_datetime)}
            {days > 0 && <sup> +{days}</sup>}
          </span>
        )}
        <span className="fr-dotted">
          <span>{formatDuration(totalMinutes(offer))}</span>
        </span>
        <span className="fr-codes">
          <span>{start?.departure_airport_code}</span>
          <span>{end?.arrival_airport_code}</span>
        </span>
      </span>
      <span className="fr-stops">
        {stopsText(offer)}
        <BaggageBadge offer={offer} />
      </span>
    </span>
  );
}

function Timeline({ offer }: { offer: FlightOffer }) {
  return (
    <ol className="timeline">
      {offer.legs.map((leg, i) => {
        const next = offer.legs[i + 1];
        return (
          <li key={`${leg.flight_number}-${i}`}>
            <div className="tl-flight">
              <div className="tl-stop">
                <b>{localTime(leg.departure_datetime)}</b>{" "}
                {airportLabel(leg.departure_airport, leg.departure_airport_code)}
              </div>
              <div className="tl-info">
                {formatDuration(leg.duration_minutes)} · {leg.airline} {leg.flight_number}
                {leg.operating_airline && ` · operated by ${leg.operating_airline}`}
              </div>
              <div className="tl-stop">
                <b>{localTime(leg.arrival_datetime)}</b>{" "}
                {airportLabel(leg.arrival_airport, leg.arrival_airport_code)}
              </div>
            </div>
            {next && (
              <div className="tl-layover">
                {formatDuration(minutesBetween(leg.arrival_datetime, next.departure_datetime))}{" "}
                layover · {layoverPlace(leg)}
                {isOvernight(leg, next) && <span className="tl-badge">Overnight</span>}
                {changesAirport(leg, next) && <span className="tl-badge warn">Airport change</span>}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function ExternalLink({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

// "Book" is the offer's deep_link and only shows when there is one. "Go to
// <airline>" shows for every airline of the trip that is in the static map.
function Links({
  deepLink,
  offers,
  bookLabel,
}: {
  deepLink?: string | null;
  offers: FlightOffer[];
  bookLabel: string;
}) {
  const codes = offers.flatMap((o) =>
    o.legs.length > 0 ? o.legs.map((leg) => leg.airline_code) : [o.primary_airline_code],
  );
  const known = [...new Set(codes)].filter((c): c is string => !!c && !!airlineUrl(c));
  if (!deepLink && known.length === 0) return null;
  return (
    <div className="links">
      {deepLink && <ExternalLink href={deepLink}>{bookLabel}</ExternalLink>}
      {known.map((code) => (
        <ExternalLink key={code} href={airlineUrl(code)!}>
          {`Go to ${AIRLINES[code.toUpperCase()].name}`}
        </ExternalLink>
      ))}
    </div>
  );
}

export function FlightRow({
  directions,
  price,
  currency,
  deepLink,
  onChoose,
  pricePrefix,
  caption,
  review = false,
  bookLabel = "Book",
  travelers = 1,
}: Props) {
  const [open, setOpen] = useState(review);
  const detailId = useId();
  const offers = directions.map((d) => d.offer);
  const roundTrip = directions.length > 1;

  return (
    <li className={`flight-row${open ? " open" : ""}${onChoose ? " has-choose" : ""}`}>
      <button
        type="button"
        className="fr-summary"
        aria-expanded={open}
        aria-controls={detailId}
        onClick={() => setOpen(!open)}
      >
        <span className="fr-lines">
          {directions.map((d, i) => (
            <Summary key={i} direction={d} />
          ))}
        </span>
        <span className="fr-price">
          {pricePrefix && <small className="fr-from">{pricePrefix}</small>}
          <strong>{formatPrice(price, currency)}</strong>
          <small>{caption ?? (roundTrip ? "round trip" : "one way")}</small>
          {travelers > 1 && <small className="fr-travelers">total for {travelers} travelers</small>}
        </span>
      </button>
      {onChoose && (
        <button type="button" className="fr-choose" onClick={onChoose}>
          Choose
        </button>
      )}
      {open && (
        <div className="fr-detail" id={detailId}>
          {directions.map((d, i) => (
            <section key={i}>
              {d.label && <h4>{d.label}</h4>}
              <Timeline offer={d.offer} />
            </section>
          ))}
          {review && <Links deepLink={deepLink} offers={offers} bookLabel={bookLabel} />}
        </div>
      )}
    </li>
  );
}
