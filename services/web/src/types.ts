// Shapes of the flights-api responses (see services/api/docs and shared/schemas.py).

export interface Leg {
  airline: string;
  flight_number: string;
  departure_airport: string;
  arrival_airport: string;
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
  outbound: FlightOffer;
  return: FlightOffer;
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
