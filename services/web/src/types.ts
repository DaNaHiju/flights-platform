// Shapes of the flights-api responses (see services/api/docs and shared/schemas.py).

export interface Leg {
  airline: string;
  flight_number: string;
  departure_airport: string;
  arrival_airport: string;
  departure_datetime: string;
  arrival_datetime: string;
  duration_minutes: number;
}

export interface FlightOffer {
  offer_id: string;
  price: number;
  currency: string;
  duration_minutes: number;
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
