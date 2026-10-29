import { airlineUrl } from "./airlines";
import { googleFlightsUrl } from "./links";
import type { FlightOffer, RoundTripOffer } from "./types";

function formatDuration(minutes: number): string {
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function describe(offer: FlightOffer): string {
  const stops = offer.stops === 0 ? "directo" : `${offer.stops} escala(s)`;
  return `${offer.primary_airline} · ${stops} · ${formatDuration(offer.duration_minutes)}`;
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

// "Reservar" always shows; "Ir a <airline>" only for airlines in the static map.
function Links({ bookUrl, airlines }: LinksProps) {
  const known = [...new Set(airlines)].filter((name) => airlineUrl(name));
  return (
    <span className="links">
      <ExternalLink href={bookUrl}>Reservar</ExternalLink>
      {known.map((name) => (
        <ExternalLink key={name} href={airlineUrl(name)!}>
          {`Ir a ${name}`}
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
      · {describe(offer)}{" "}
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
      · ida y vuelta
      <div>Ida: {describe(offer.outbound)}</div>
      <div>Vuelta: {describe(offer.return)}</div>
      <Links
        bookUrl={googleFlightsUrl(origin, destination, date, returnDate)}
        airlines={[offer.outbound.primary_airline, offer.return.primary_airline]}
      />
    </li>
  );
}
