// Which place a search or a deal is about, for the destination photo.
import { countryName } from "./format";
import type { Deal, DestinationPlace, FlightOffer, RoundTripOffer, SearchQuery } from "./types";

/** "Hanoi, Vietnam"; just the city when the country is unknown. */
export function placeTitle({ city, country }: DestinationPlace): string {
  return country ? `${city}, ${country}` : city;
}

/** The destination of a deal, or null for deals cached without a city. */
export function dealPlace(deal: Deal): DestinationPlace | null {
  if (!deal.destination_city) return null;
  return {
    city: deal.destination_city,
    country: deal.destination_country_code ? countryName(deal.destination_country_code) : "",
  };
}

// Where the last flight of an offer lands, when the API said which city.
function arrivalPlace(offer: FlightOffer): DestinationPlace | null {
  const last = offer.legs[offer.legs.length - 1];
  if (!last?.arrival_city) return null;
  return {
    city: last.arrival_city,
    country: last.arrival_country_code ? countryName(last.arrival_country_code) : "",
  };
}

/**
 * The searched destination: the place picked in the autocomplete or, when a bare
 * code was typed, the arrival city of the first result that names one.
 */
export function destinationOf(
  query: SearchQuery,
  offers: (FlightOffer | RoundTripOffer)[],
): DestinationPlace | null {
  if (query.destinationPlace) return query.destinationPlace;
  for (const offer of offers) {
    const place = arrivalPlace("outbound" in offer ? offer.outbound : offer);
    if (place) return place;
  }
  return null;
}
