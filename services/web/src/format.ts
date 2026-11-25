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

/**
 * "2099-01-01T08:00:00+02:00" -> "08:00". The API sends each airport's LOCAL
 * time with its offset; slicing keeps it as is. Formatting through Date would
 * convert it to the viewer's timezone, which is wrong for flight times.
 */
export function localTime(iso: string): string {
  return iso.slice(11, 16);
}

/** Days between the calendar dates of two local timestamps (0, 1, ...). */
export function dayDifference(fromIso: string, toIso: string): number {
  const from = Date.UTC(+fromIso.slice(0, 4), +fromIso.slice(5, 7) - 1, +fromIso.slice(8, 10));
  const to = Date.UTC(+toIso.slice(0, 4), +toIso.slice(5, 7) - 1, +toIso.slice(8, 10));
  return Math.round((to - from) / 86_400_000);
}

/** Search code for display: "MAD+" (one airport) shows as "MAD". */
export function displayCode(code: string): string {
  return code.replace(/\+$/, "");
}
