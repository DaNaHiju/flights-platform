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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * "2099-01-12" -> "12 Jan". Read from the string, not through Date: a calendar
 * date has no timezone, and Date would shift it for some viewers.
 */
export function formatDay(isoDate: string): string {
  return `${+isoDate.slice(8, 10)} ${MONTHS[+isoDate.slice(5, 7) - 1]}`;
}

/** Days between the calendar dates of two local timestamps (0, 1, ...). */
export function dayDifference(fromIso: string, toIso: string): number {
  const from = Date.UTC(+fromIso.slice(0, 4), +fromIso.slice(5, 7) - 1, +fromIso.slice(8, 10));
  const to = Date.UTC(+toIso.slice(0, 4), +toIso.slice(5, 7) - 1, +toIso.slice(8, 10));
  return Math.round((to - from) / 86_400_000);
}

/**
 * Wall-clock minutes of a local timestamp, offset ignored: "2099-01-01T08:30:00+02:00"
 * and "2099-01-01T08:30:00-05:00" give the same number. For ordering flights by
 * the time shown on the ticket; never for elapsed time (see minutesBetween).
 */
export function localMinutes(iso: string): number {
  return (
    Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10), +iso.slice(11, 13), +iso.slice(14, 16)) /
    60_000
  );
}

/** Search code for display: "MAD+" (one airport) shows as "MAD". */
export function displayCode(code: string): string {
  return code.replace(/\+$/, "");
}

/**
 * 1234 + "ILS" -> "₪1,234". The currency is whatever the API sent: nothing is
 * hardcoded here. Whole units only, like the fare listings people compare it to.
 * A code Intl does not know falls back to "1234 XYZ" instead of crashing.
 */
export function formatPrice(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${Math.round(amount)} ${currency}`;
  }
}

/**
 * Minutes between two timestamps that carry their UTC offsets, e.g. the arrival
 * at a layover airport and the next departure. Date.parse honours the offsets, so
 * the result is the real elapsed time, not a difference of local clocks.
 */
export function minutesBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(toIso) - Date.parse(fromIso)) / 60_000);
}
