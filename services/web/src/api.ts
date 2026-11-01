import type { Deal, FlightOffer, RoundTripOffer } from "./types";

// Same origin: nginx (or the vite dev server) forwards /api/* to flights-api.
const BASE = "/api";

export const PROVIDER_DOWN_MESSAGE =
  "The flight provider is not responding right now. Please try again in a few minutes.";

const ERROR_MESSAGES: Record<string, string> = {
  invalid_iata_code: "Invalid airport code. Use 3 letters, for example EZE.",
  invalid_date_format: "The date format is not valid.",
  date_in_past: "The date must be today or later.",
  return_before_departure: "The return cannot be before the departure.",
  deals_not_available: "No deals have been calculated yet.",
};

export class ApiError extends Error {}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`);
  } catch {
    throw new ApiError("Could not connect to the server.");
  }

  if (res.status === 502) {
    throw new ApiError(PROVIDER_DOWN_MESSAGE);
  }
  if (!res.ok) {
    // The API answers errors as a flat {"error": "<code>"} body.
    const body = (await res.json().catch(() => ({}))) as { error?: string };
    throw new ApiError(
      (body.error && ERROR_MESSAGES[body.error]) ||
        `Unexpected error (HTTP ${res.status}).`,
    );
  }
  return (await res.json()) as T;
}

export async function searchFlights(
  origin: string,
  destination: string,
  date: string,
): Promise<FlightOffer[]> {
  const query = new URLSearchParams({ origin, destination, date });
  const data = await get<{ results: FlightOffer[] }>(`/flights?${query}`);
  return data.results;
}

export async function searchRoundTrip(
  origin: string,
  destination: string,
  date: string,
  returnDate: string,
): Promise<RoundTripOffer[]> {
  const query = new URLSearchParams({
    origin,
    destination,
    date,
    return_date: returnDate,
  });
  const data = await get<{ results: RoundTripOffer[] }>(`/flights?${query}`);
  return data.results;
}

export async function listDeals(): Promise<Deal[]> {
  const data = await get<{ deals: Deal[] }>("/deals");
  return data.deals;
}
