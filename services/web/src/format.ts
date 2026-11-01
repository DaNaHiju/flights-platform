// Display helpers shared by offers and deals.

/** 380 -> "6h 20m"; whole hours -> "6h"; under an hour -> "45m". */
export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

/** "IT" -> "Italy"; the code itself when the runtime does not know it. */
export function countryName(code: string): string {
  try {
    return regionNames.of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

export interface Place {
  code?: string | null;
  city?: string | null;
  countryCode?: string | null;
  airportName?: string | null;
}

/**
 * "Rome, Italy (FCO)" when city and country are known. Otherwise the airport
 * name (as before this feature), or just the code.
 */
export function placeLabel({ code, city, countryCode, airportName }: Place): string {
  if (city && countryCode) {
    const base = `${city}, ${countryName(countryCode)}`;
    return code ? `${base} (${code})` : base;
  }
  return airportName || code || "";
}

/** The airport name as secondary text, only when the main label is not already it. */
export function secondaryAirport({ city, countryCode, airportName }: Place): string | null {
  return city && countryCode && airportName ? airportName : null;
}
