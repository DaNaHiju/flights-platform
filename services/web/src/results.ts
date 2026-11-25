// Pure logic for the result list: duplicates, ordering and paging. No React here.
import type { FlightOffer, RoundTripOffer } from "./types";

export type SortKey = "best" | "cheapest" | "fastest";

/** What the list needs to know about one result, one way or round trip. */
export interface Ranked<T> {
  item: T;
  // Stable identity, so an expanded row stays with its offer when the order changes.
  key: string;
  price: number;
  currency: string;
  duration: number;
  stops: number;
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

export function rankOneWay(offer: FlightOffer): Ranked<FlightOffer> {
  return {
    item: offer,
    key: offer.offer_id,
    price: offer.price,
    currency: offer.currency,
    duration: totalMinutes(offer),
    stops: offer.stops,
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

/** A new array ordered for the tab; ties fall back to the other criterion. */
export function sortRanked<T>(list: Ranked<T>[], key: SortKey): Ranked<T>[] {
  const minPrice = Math.min(...list.map((r) => r.price));
  const minDuration = Math.min(...list.map((r) => r.duration));
  const by: Record<SortKey, (r: Ranked<T>) => number[]> = {
    best: (r) => [bestScore(r, minPrice, minDuration), r.price],
    cheapest: (r) => [r.price, r.duration],
    fastest: (r) => [r.duration, r.price],
  };
  return [...list].sort((a, b) => {
    const x = by[key](a);
    const y = by[key](b);
    return x[0] - y[0] || x[1] - y[1];
  });
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
    signature: null,
  };
}
