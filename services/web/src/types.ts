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
