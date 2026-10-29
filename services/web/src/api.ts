import type { Deal, FlightOffer } from "./types";

// Same origin: nginx (or the vite dev server) forwards /api/* to flights-api.
const BASE = "/api";

export const PROVIDER_DOWN_MESSAGE =
  "El proveedor de vuelos no responde ahora. Probá de nuevo en unos minutos.";

const ERROR_MESSAGES: Record<string, string> = {
  invalid_iata_code: "Código de aeropuerto inválido. Usá 3 letras, por ejemplo EZE.",
  invalid_date_format: "La fecha no tiene un formato válido.",
  date_in_past: "La fecha tiene que ser hoy o posterior.",
  deals_not_available: "Todavía no hay ofertas calculadas.",
};

export class ApiError extends Error {}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`);
  } catch {
    throw new ApiError("No se pudo conectar con el servidor.");
  }

  if (res.status === 502) {
    throw new ApiError(PROVIDER_DOWN_MESSAGE);
  }
  if (!res.ok) {
    // The API answers errors as a flat {"error": "<code>"} body.
    const body = (await res.json().catch(() => ({}))) as { error?: string };
    throw new ApiError(
      (body.error && ERROR_MESSAGES[body.error]) ||
        `Error inesperado (HTTP ${res.status}).`,
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

export async function listDeals(): Promise<Deal[]> {
  const data = await get<{ deals: Deal[] }>("/deals");
  return data.deals;
}
