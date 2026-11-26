// Text of the checked-bag badge of one direction. Pure: no React here.
import type { CheckedBag, FlightOffer } from "./types";

export interface BaggageInfo {
  // "unknown": the API did not say. It must never read as "no bag".
  kind: "included" | "none" | "unknown";
  text: string;
}

export const BAGGAGE_UNKNOWN = "Checked bag info not available";
export const BAGGAGE_NONE = "No checked bag";

// "KG" -> "kg"; anything else is shown as sent, in lower case.
const unit = (u?: string | null) => (u ?? "kg").toLowerCase();

/** What one allowance gives, or null when it is an explicit zero. */
function allowanceText(bag: CheckedBag): string | null {
  const weight = bag.weight_amount ? `${bag.weight_amount} ${unit(bag.weight_unit)}` : null;
  if (bag.type === "piece") {
    const pieces = bag.quantity ?? 1;
    if (pieces <= 0) return null;
    const label = `${pieces} checked bag${pieces === 1 ? "" : "s"}`;
    return weight ? `${label} · ${weight}` : label;
  }
  // A weight allowance: the bags are not counted, only their weight.
  return weight ? `Checked bag · ${weight}` : null;
}

// Whether the allowance applies to every flight of the direction. An empty
// list means the provider did not say which, which is read as all of them.
function coversEveryFlight(bag: CheckedBag, flights: number): boolean {
  const legs = bag.applicable_legs ?? [];
  if (legs.length === 0) return true;
  for (let n = 1; n <= flights; n++) if (!legs.includes(n)) return false;
  return true;
}

/**
 * The badge for one direction:
 *  - checked_bags missing or null  -> unknown (older caches, or the airline did not say)
 *  - [] or only zero allowances    -> "No checked bag" (the API said so)
 *  - otherwise                     -> "1 checked bag · 23 kg", and "· some flights only"
 *    when an allowance does not cover every flight of a connection.
 */
export function baggageInfo(offer: FlightOffer): BaggageInfo {
  if (offer.checked_bags == null) return { kind: "unknown", text: BAGGAGE_UNKNOWN };

  const flights = Math.max(offer.legs.length, 1);
  const given = offer.checked_bags
    .map((bag) => ({ bag, text: allowanceText(bag) }))
    .filter((x): x is { bag: CheckedBag; text: string } => x.text !== null);
  if (given.length === 0) return { kind: "none", text: BAGGAGE_NONE };

  const partial = given.some(({ bag }) => !coversEveryFlight(bag, flights));
  const text = given.map((x) => x.text).join(" + ");
  return { kind: "included", text: partial ? `${text} · some flights only` : text };
}
