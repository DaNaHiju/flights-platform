// Shapes of the flights-api responses (see services/api/docs and shared/schemas.py).

export interface Leg {
  // Resolved airline name; the IATA code is in airline_code.
  airline: string;
  airline_code?: string | null;
  flight_number: string;
  // Name of the airline that actually flies it, when it differs (codeshare).
  operating_airline?: string | null;
  departure_airport: string;
  arrival_airport: string;
  // Local time at each airport with its UTC offset, as the API sends it.
  // Display it as is: never convert it to the viewer's timezone.
  departure_datetime: string;
  arrival_datetime: string;
  duration_minutes: number;
  // Added fields; absent in responses served from older caches, null when unknown.
  departure_airport_code?: string | null;
  arrival_airport_code?: string | null;
  departure_city?: string | null;
  arrival_city?: string | null;
  departure_country_code?: string | null;
  arrival_country_code?: string | null;
}

export interface FlightOffer {
  offer_id: string;
  price: number;
  currency: string;
  duration_minutes: number;
  total_duration_minutes?: number;
  stops: number;
  primary_airline: string;
  primary_airline_code?: string | null;
  carriers?: string[];
  merchant?: string | null;
  // Redirects to the airline's booking page. Absent on some offers.
  deep_link?: string | null;
  legs: Leg[];
}

export interface Deal {
  destination: string;
  departure_date: string;
  price: number;
  currency: string;
  airline: string;
  // Added fields; deals cached before they existed lack them entirely.
  origin?: string | null;
  origin_airport_name?: string | null;
  origin_city?: string | null;
  origin_country_code?: string | null;
  destination_airport_name?: string | null;
  destination_city?: string | null;
  destination_country_code?: string | null;
  total_duration_minutes?: number | null;
}

// GET /flights with return_date: one item per outbound + return pair, priced as a whole.
export interface RoundTripOffer {
  price: number;
  currency: string;
  merchant?: string | null;
  deep_link?: string | null;
  outbound: FlightOffer;
  return: FlightOffer;
}

// GET /locations: one airport or city for the origin/destination typeahead.
export interface Location {
  id: string;
  iata_code: string;
  sub_type: "AIRPORT" | "CITY";
  name: string;
  detailed_name?: string | null;
  city_name?: string | null;
  city_code?: string | null;
  country_name?: string | null;
  country_code?: string | null;
  // What to send as origin/destination: "MAD+" pins one airport, "MAD" a whole city.
  search_code: string;
}

export type TripMode = "one-way" | "round-trip" | "multi-city";

export interface SearchQuery {
  mode: TripMode;
  origin: string;
  destination: string;
  date: string;
  // round-trip only
  returnDate: string;
  // multi-city only: the second, independent leg
  origin2: string;
  destination2: string;
  date2: string;
}
