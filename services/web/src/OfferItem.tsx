import { airlineDisplayName, airlineUrl } from "./airlines";
import { formatDuration, placeLabel, secondaryAirport, type Place } from "./format";
import { googleFlightsUrl } from "./links";
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
  return `${airlineDisplayName(offer.primary_airline)} · ${stops} · ${formatDuration(totalMinutes(offer))}`;
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
          {airlineDisplayName(leg.airline)} {leg.flight_number}:{" "}
          {placeLabel(departurePlace(leg))} → {placeLabel(arrivalPlace(leg))} ·{" "}
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
  bookUrl: string;
  airlines: string[];
}

// "Book" always shows; "Go to <airline>" only for airlines in the static map.
function Links({ bookUrl, airlines }: LinksProps) {
  const known = [...new Set(airlines)].filter((name) => airlineUrl(name));
  return (
    <span className="links">
      <ExternalLink href={bookUrl}>Book</ExternalLink>
      {known.map((name) => (
        <ExternalLink key={name} href={airlineUrl(name)!}>
          {`Go to ${airlineDisplayName(name)}`}
        </ExternalLink>
      ))}
    </span>
  );
}

interface OneWayProps {
  offer: FlightOffer;
  origin: string;
  destination: string;
  date: string;
}

export function OneWayItem({ offer, origin, destination, date }: OneWayProps) {
  return (
    <li>
      <strong>
        {offer.price} {offer.currency}
      </strong>{" "}
      · {describe(offer)}
      <Route offer={offer} />
      <Segments offer={offer} />
      <Links
        bookUrl={googleFlightsUrl(origin, destination, date)}
        airlines={[offer.primary_airline]}
      />
    </li>
  );
}

interface RoundTripProps {
  offer: RoundTripOffer;
  origin: string;
  destination: string;
  date: string;
  returnDate: string;
}

export function RoundTripItem({
  offer,
  origin,
  destination,
  date,
  returnDate,
}: RoundTripProps) {
  return (
    <li>
      <strong>
        {offer.price} {offer.currency}
      </strong>{" "}
      · round trip
      <div>Outbound: {describe(offer.outbound)}</div>
      <Route offer={offer.outbound} />
      <Segments offer={offer.outbound} />
      <div>Return: {describe(offer.return)}</div>
      <Route offer={offer.return} />
      <Segments offer={offer.return} />
      <Links
        bookUrl={googleFlightsUrl(origin, destination, date, returnDate)}
        airlines={[offer.outbound.primary_airline, offer.return.primary_airline]}
      />
    </li>
  );
}
