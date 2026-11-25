import { AIRLINES, airlineUrl } from "./airlines";
import {
  dayDifference,
  formatDuration,
  localTime,
  placeLabel,
  secondaryAirport,
  type Place,
} from "./format";
import type { FlightOffer, Leg, RoundTripOffer } from "./types";

function departurePlace(leg: Leg): Place {
  return {
    code: leg.departure_airport_code,
    city: leg.departure_city,
    countryCode: leg.departure_country_code,
    airportName: leg.departure_airport,
  };
}

function arrivalPlace(leg: Leg): Place {
  return {
    code: leg.arrival_airport_code,
    city: leg.arrival_city,
    countryCode: leg.arrival_country_code,
    airportName: leg.arrival_airport,
  };
}

function PlaceText({ place }: { place: Place }) {
  const secondary = secondaryAirport(place);
  return (
    <>
      {placeLabel(place)}
      {secondary && <small className="airport"> {secondary}</small>}
    </>
  );
}

function totalMinutes(offer: FlightOffer): number {
  return offer.total_duration_minutes ?? offer.duration_minutes;
}

function describe(offer: FlightOffer): string {
  const stops = offer.stops === 0 ? "Direct" : `${offer.stops} stop${offer.stops > 1 ? "s" : ""}`;
  const airlines = offer.carriers?.length ? offer.carriers.join(" + ") : offer.primary_airline;
  return `${airlines} · ${stops} · ${formatDuration(totalMinutes(offer))}`;
}

// "08:00 → 12:15 (+1)": local times at each airport, as sent by the API.
function Times({ offer }: { offer: FlightOffer }) {
  const first = offer.legs[0];
  const last = offer.legs[offer.legs.length - 1];
  if (!first || !last) return null;
  const days = dayDifference(first.departure_datetime, last.arrival_datetime);
  return (
    <div className="times">
      {localTime(first.departure_datetime)} → {localTime(last.arrival_datetime)}
      {days > 0 && <sup> +{days}</sup>}
    </div>
  );
}

// "Tel Aviv, Israel (TLV) → Rome, Italy (FCO)" from the first and last leg. Offers
// without legs (or without the added fields) degrade to what is available.
function Route({ offer }: { offer: FlightOffer }) {
  const first = offer.legs[0];
  const last = offer.legs[offer.legs.length - 1];
  if (!first || !last) return null;
  return (
    <div className="route">
      <PlaceText place={departurePlace(first)} /> → <PlaceText place={arrivalPlace(last)} />
    </div>
  );
}

// Every segment with its own duration; between two of them, the layover airport.
function Segments({ offer }: { offer: FlightOffer }) {
  if (offer.legs.length < 2) return null;
  return (
    <ol className="segments">
      {offer.legs.map((leg, i) => (
        <li key={`${leg.flight_number}-${i}`}>
          {leg.airline} {leg.flight_number}
          {leg.operating_airline && ` (operated by ${leg.operating_airline})`}:{" "}
          {placeLabel(departurePlace(leg))} {localTime(leg.departure_datetime)} →{" "}
          {placeLabel(arrivalPlace(leg))} {localTime(leg.arrival_datetime)} ·{" "}
          {formatDuration(leg.duration_minutes)}
          {i < offer.legs.length - 1 && (
            <div className="layover">Layover in {placeLabel(arrivalPlace(leg))}</div>
          )}
        </li>
      ))}
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

interface LinksProps {
  deepLink?: string | null;
  airlineCodes: (string | null | undefined)[];
}

// "Book" goes to the airline's own booking page (the offer's deep_link) and
// only shows when the offer has one. "Go to <airline>" shows for airlines in
// the static map.
function Links({ deepLink, airlineCodes }: LinksProps) {
  const known = [...new Set(airlineCodes)].filter(
    (code): code is string => !!code && !!airlineUrl(code),
  );
  if (!deepLink && known.length === 0) return null;
  return (
    <span className="links">
      {deepLink && <ExternalLink href={deepLink}>Book</ExternalLink>}
      {known.map((code) => (
        <ExternalLink key={code} href={airlineUrl(code)!}>
          {`Go to ${AIRLINES[code].name}`}
        </ExternalLink>
      ))}
    </span>
  );
}

export function OneWayItem({ offer }: { offer: FlightOffer }) {
  return (
    <li>
      <strong>
        {offer.price} {offer.currency}
      </strong>{" "}
      · {describe(offer)}
      <Route offer={offer} />
      <Times offer={offer} />
      <Segments offer={offer} />
      <Links deepLink={offer.deep_link} airlineCodes={[offer.primary_airline_code]} />
    </li>
  );
}

export function RoundTripItem({ offer }: { offer: RoundTripOffer }) {
  return (
    <li>
      <strong>
        {offer.price} {offer.currency}
      </strong>{" "}
      · round trip
      <div>Outbound: {describe(offer.outbound)}</div>
      <Route offer={offer.outbound} />
      <Times offer={offer.outbound} />
      <Segments offer={offer.outbound} />
      <div>Return: {describe(offer.return)}</div>
      <Route offer={offer.return} />
      <Times offer={offer.return} />
      <Segments offer={offer.return} />
      <Links
        deepLink={offer.deep_link}
        airlineCodes={[offer.outbound.primary_airline_code, offer.return.primary_airline_code]}
      />
    </li>
  );
}
