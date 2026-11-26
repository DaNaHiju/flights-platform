// Pure logic for the result list: duplicates, ordering and paging. No React here.
import { localMinutes } from "./format";
import type { FlightOffer, RoundTripOffer } from "./types";

export type SortKey = "best" | "cheapest" | "fastest" | "departure" | "arrival" | "stops";

// The "Sort by" menu. The first three are also the tabs: "Price" is the
// Cheapest tab and "Duration" the Fastest one, so both controls share one state.
export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "best", label: "Best" },
  { key: "cheapest", label: "Price" },
  { key: "fastest", label: "Duration" },
  { key: "departure", label: "Departure time" },
  { key: "arrival", label: "Arrival time" },
  { key: "stops", label: "Stops" },
];

/** What the list needs to know about one result, one way or round trip. */
export interface Ranked<T> {
  item: T;
  // Stable identity, so an expanded row stays with its offer when the order changes.
  key: string;
  price: number;
  currency: string;
  duration: number;
  stops: number;
  // Local departure of the first flight and local arrival of the last one of the
  // leg this step shows (the return, in the return step), as the API sent them.
  // Null when the offer has no legs.
  departure: string | null;
  arrival: string | null;
  // Airline names on the leg this step shows, once each, in flying order.
  airlines: string[];
  // Same signature = same flights. Null when the offer has no legs to compare.
  signature: string | null;
}

export function totalMinutes(offer: FlightOffer): number {
  return offer.total_duration_minutes ?? offer.duration_minutes;
}

// Flight number + departure time of every leg: "LY381@2099-01-01T08:00:00|...".
export function offerSignature(offer: FlightOffer): string | null {
  if (offer.legs.length === 0) return null;
  return offer.legs.map((leg) => `${leg.flight_number}@${leg.departure_datetime}`).join("|");
}

/** Every airline on the given directions, once, in flying order: "ITA Airways, ANA". */
export function airlinesOf(offers: FlightOffer[]): string[] {
  const names = offers.flatMap((o) => o.legs.map((leg) => leg.airline));
  const unique = [...new Set(names.filter(Boolean))];
  if (unique.length > 0) return unique;
  return [...new Set(offers.flatMap((o) => o.carriers ?? [o.primary_airline]))];
}

// First departure and last arrival of one direction.
function endpoints(offer: FlightOffer): { departure: string | null; arrival: string | null } {
  const legs = offer.legs;
  return {
    departure: legs[0]?.departure_datetime ?? null,
    arrival: legs[legs.length - 1]?.arrival_datetime ?? null,
  };
}

export function rankOneWay(offer: FlightOffer): Ranked<FlightOffer> {
  return {
    item: offer,
    key: offer.offer_id,
    price: offer.price,
    currency: offer.currency,
    duration: totalMinutes(offer),
    stops: offer.stops,
    ...endpoints(offer),
    airlines: airlinesOf([offer]),
    signature: offerSignature(offer),
  };
}

export function rankRoundTrip(offer: RoundTripOffer): Ranked<RoundTripOffer> {
  const out = offerSignature(offer.outbound);
  const back = offerSignature(offer.return);
  return {
    item: offer,
    key: `${offer.outbound.offer_id}-${offer.return.offer_id}`,
    price: offer.price,
    currency: offer.currency,
    duration: totalMinutes(offer.outbound) + totalMinutes(offer.return),
    stops: offer.outbound.stops + offer.return.stops,
    ...endpoints(offer.outbound),
    airlines: airlinesOf([offer.outbound, offer.return]),
    signature: out && back ? `${out}||${back}` : null,
  };
}

/**
 * Two offers with the same flights in every leg (same number and departure time)
 * are the same trip sold twice: keep the cheapest. Offers without legs cannot be
 * compared, so they are always kept. The order of the survivors is preserved.
 */
export function dedupe<T>(list: Ranked<T>[]): Ranked<T>[] {
  const cheapest = new Map<string, Ranked<T>>();
  for (const r of list) {
    if (r.signature === null) continue;
    const seen = cheapest.get(r.signature);
    if (!seen || r.price < seen.price) cheapest.set(r.signature, r);
  }
  return list.filter((r) => r.signature === null || cheapest.get(r.signature) === r);
}

/**
 * "Best" score, lower is better:
 *
 *   price / cheapestPrice  +  duration / shortestDuration  +  0.25 * stops
 *
 * Price and duration are each measured against the best value in the list, so
 * the cheapest offer scores 1 on price and the fastest scores 1 on duration; an
 * offer twice as expensive adds 2 instead of 1. Each stop costs a quarter of
 * that: a stop is worth avoiding unless it saves about a quarter of the price.
 */
export function bestScore(r: Ranked<unknown>, minPrice: number, minDuration: number): number {
  return r.price / minPrice + r.duration / minDuration + 0.25 * r.stops;
}

// Local clock of a departure/arrival; a missing one sorts last.
const clock = (iso: string | null): number => (iso === null ? Infinity : localMinutes(iso));

/** A new array in the order of *key*; ties fall back to the price (or the duration). */
export function sortRanked<T>(list: Ranked<T>[], key: SortKey): Ranked<T>[] {
  const minPrice = Math.min(...list.map((r) => r.price));
  const minDuration = Math.min(...list.map((r) => r.duration));
  const by: Record<SortKey, (r: Ranked<T>) => number[]> = {
    best: (r) => [bestScore(r, minPrice, minDuration), r.price],
    cheapest: (r) => [r.price, r.duration],
    fastest: (r) => [r.duration, r.price],
    departure: (r) => [clock(r.departure), r.price],
    arrival: (r) => [clock(r.arrival), r.price],
    // Fewest stops first; among equals, the cheapest.
    stops: (r) => [r.stops, r.price],
  };
  return [...list].sort((a, b) => {
    const x = by[key](a);
    const y = by[key](b);
    return x[0] - y[0] || x[1] - y[1];
  });
}

// ── Filters ──────────────────────────────────────────────────────────────────
// Applied in the browser to the list of the current step. Within one group
// (stops, airlines, times) an offer needs to match ANY ticked box; across
// groups it needs to match ALL of them. An untouched group filters nothing.

export type StopsBucket = "0" | "1" | "2+";
export type TimeBucket = "morning" | "afternoon" | "evening" | "night";

export const STOPS_BUCKETS: { key: StopsBucket; label: string }[] = [
  { key: "0", label: "Nonstop" },
  { key: "1", label: "1 stop" },
  { key: "2+", label: "2+ stops" },
];

// Local hours [from, to) of the departure.
export const TIME_BUCKETS: { key: TimeBucket; label: string; from: number; to: number }[] = [
  { key: "morning", label: "Morning (05–12)", from: 5, to: 12 },
  { key: "afternoon", label: "Afternoon (12–18)", from: 12, to: 18 },
  { key: "evening", label: "Evening (18–24)", from: 18, to: 24 },
  { key: "night", label: "Night (00–05)", from: 0, to: 5 },
];

export interface Filters {
  stops: StopsBucket[];
  airlines: string[];
  times: TimeBucket[];
  // Upper bounds; null = no limit. Duration is in hours.
  maxPrice: number | null;
  maxDurationHours: number | null;
}

export const NO_FILTERS: Filters = {
  stops: [],
  airlines: [],
  times: [],
  maxPrice: null,
  maxDurationHours: null,
};

export function stopsBucket(stops: number): StopsBucket {
  return stops <= 0 ? "0" : stops === 1 ? "1" : "2+";
}

/** The bucket of a local timestamp ("...T08:30:00+02:00" -> morning), by its own hour. */
export function timeBucket(iso: string): TimeBucket {
  const hour = +iso.slice(11, 13);
  return TIME_BUCKETS.find((b) => hour >= b.from && hour < b.to)!.key;
}

/** How many filter groups are narrowing the list (for the button badge and Clear). */
export function activeFilterCount(f: Filters): number {
  return (
    (f.stops.length > 0 ? 1 : 0) +
    (f.airlines.length > 0 ? 1 : 0) +
    (f.times.length > 0 ? 1 : 0) +
    (f.maxPrice !== null ? 1 : 0) +
    (f.maxDurationHours !== null ? 1 : 0)
  );
}

export function applyFilters<T>(list: Ranked<T>[], f: Filters): Ranked<T>[] {
  return list.filter((r) => {
    if (f.stops.length > 0 && !f.stops.includes(stopsBucket(r.stops))) return false;
    if (f.airlines.length > 0 && !r.airlines.some((a) => f.airlines.includes(a))) return false;
    // An offer without a departure time cannot be placed in a time of day.
    if (f.times.length > 0 && (r.departure === null || !f.times.includes(timeBucket(r.departure)))) {
      return false;
    }
    if (f.maxPrice !== null && r.price > f.maxPrice) return false;
    if (f.maxDurationHours !== null && r.duration > f.maxDurationHours * 60) return false;
    return true;
  });
}

/** What the panel offers, from the whole (unfiltered) list so the controls stay put. */
export interface Facets {
  stopCounts: Record<StopsBucket, number>;
  airlines: string[];
  // Whole units, rounded outwards so the cheapest and the priciest both fit.
  minPrice: number;
  maxPrice: number;
  minHours: number;
  maxHours: number;
  currency: string;
}

export function buildFacets<T>(list: Ranked<T>[]): Facets {
  const stopCounts: Record<StopsBucket, number> = { "0": 0, "1": 0, "2+": 0 };
  for (const r of list) stopCounts[stopsBucket(r.stops)] += 1;
  const prices = list.map((r) => r.price);
  const hours = list.map((r) => r.duration / 60);
  return {
    stopCounts,
    airlines: [...new Set(list.flatMap((r) => r.airlines))].sort((a, b) => a.localeCompare(b)),
    minPrice: Math.floor(Math.min(...prices)),
    maxPrice: Math.ceil(Math.max(...prices)),
    minHours: Math.floor(Math.min(...hours)),
    maxHours: Math.ceil(Math.max(...hours)),
    currency: list[0]?.currency ?? "",
  };
}

export const PAGE_SIZE = 10;

/** One outbound flight and every round-trip pair that includes it. */
export interface OutboundGroup {
  key: string;
  // The outbound of the cheapest pair: the one whose fare the "from" price is.
  outbound: FlightOffer;
  pairs: RoundTripOffer[];
  minPrice: number;
  currency: string;
}

/**
 * Amadeus sells a round trip as ONE fare, so a return can only be chosen among
 * the pairs that came with the chosen outbound. Group the pairs by outbound
 * (same flight number and departure time in every leg) after dropping repeated
 * pairs, using only what the search already returned.
 */
export function groupByOutbound(offers: RoundTripOffer[]): OutboundGroup[] {
  const groups = new Map<string, OutboundGroup>();
  for (const { item: pair } of dedupe(offers.map(rankRoundTrip))) {
    const key = offerSignature(pair.outbound) ?? `id:${pair.outbound.offer_id}`;
    const group = groups.get(key);
    if (!group) {
      groups.set(key, {
        key,
        outbound: pair.outbound,
        pairs: [pair],
        minPrice: pair.price,
        currency: pair.currency,
      });
    } else {
      group.pairs.push(pair);
      if (pair.price < group.minPrice) {
        group.minPrice = pair.price;
        group.outbound = pair.outbound;
      }
    }
  }
  return [...groups.values()];
}

/** Step 1 of a round trip: ranked by the outbound alone, priced "from". */
export function rankGroup(group: OutboundGroup): Ranked<OutboundGroup> {
  return {
    item: group,
    key: group.key,
    price: group.minPrice,
    currency: group.currency,
    duration: totalMinutes(group.outbound),
    stops: group.outbound.stops,
    ...endpoints(group.outbound),
    airlines: airlinesOf([group.outbound]),
    signature: null,
  };
}

/** Step 2 of a round trip: ranked by the return flight, priced as the whole trip. */
export function rankReturn(pair: RoundTripOffer): Ranked<RoundTripOffer> {
  return {
    item: pair,
    key: `${pair.outbound.offer_id}-${pair.return.offer_id}`,
    price: pair.price,
    currency: pair.currency,
    duration: totalMinutes(pair.return),
    stops: pair.return.stops,
    ...endpoints(pair.return),
    airlines: airlinesOf([pair.return]),
    signature: null,
  };
}
