import { describe, expect, it } from "vitest";
import { BAGGAGE_NONE, BAGGAGE_UNKNOWN, baggageInfo } from "./baggage";
import type { CheckedBag, FlightOffer } from "./types";

function offer(checked_bags: CheckedBag[] | null | undefined, flights = 1): FlightOffer {
  const leg = {
    airline: "X",
    flight_number: "X1",
    departure_airport: "A",
    arrival_airport: "B",
    departure_datetime: "2099-01-01T08:00:00",
    arrival_datetime: "2099-01-01T10:00:00",
    duration_minutes: 120,
  };
  return {
    offer_id: "o",
    price: 1,
    currency: "ILS",
    duration_minutes: 120,
    stops: flights - 1,
    primary_airline: "X",
    legs: Array.from({ length: flights }, () => leg),
    ...(checked_bags === undefined ? {} : { checked_bags }),
  };
}

describe("baggageInfo", () => {
  it("is UNKNOWN when the field is missing or null, never 'No checked bag'", () => {
    for (const o of [offer(undefined), offer(null)]) {
      expect(baggageInfo(o)).toEqual({ kind: "unknown", text: BAGGAGE_UNKNOWN });
    }
    expect(BAGGAGE_UNKNOWN).toBe("Checked bag info not available");
  });

  it("says 'No checked bag' only when the API sent an empty list", () => {
    expect(baggageInfo(offer([]))).toEqual({ kind: "none", text: BAGGAGE_NONE });
  });

  it("an explicit zero allowance is also 'No checked bag'", () => {
    expect(baggageInfo(offer([{ type: "piece", quantity: 0 }])).kind).toBe("none");
  });

  it("a piece with its weight: '1 checked bag · 23 kg'", () => {
    const info = baggageInfo(offer([{ type: "piece", quantity: 1, weight_amount: 23, weight_unit: "KG" }]));
    expect(info).toEqual({ kind: "included", text: "1 checked bag · 23 kg" });
  });

  it("pluralises and works without a weight", () => {
    expect(baggageInfo(offer([{ type: "piece", quantity: 2 }])).text).toBe("2 checked bags");
    expect(baggageInfo(offer([{ type: "piece" }])).text).toBe("1 checked bag");
  });

  it("a weight allowance shows the weight in its unit", () => {
    expect(baggageInfo(offer([{ type: "weight", weight_amount: 20, weight_unit: "KG" }])).text).toBe(
      "Checked bag · 20 kg",
    );
    expect(baggageInfo(offer([{ type: "weight", weight_amount: 44, weight_unit: "LB" }])).text).toBe(
      "Checked bag · 44 lb",
    );
  });

  it("a weight allowance with no amount says nothing useful, so it counts as none given", () => {
    expect(baggageInfo(offer([{ type: "weight" }])).kind).toBe("none");
  });

  it("flags an allowance that covers only some flights of a connection", () => {
    const bag: CheckedBag = { type: "piece", quantity: 1, weight_amount: 23, weight_unit: "KG", applicable_legs: [1] };
    expect(baggageInfo(offer([bag], 2)).text).toBe("1 checked bag · 23 kg · some flights only");
    expect(baggageInfo(offer([{ ...bag, applicable_legs: [1, 2] }], 2)).text).toBe("1 checked bag · 23 kg");
    // not said which flights: read as all of them
    expect(baggageInfo(offer([{ ...bag, applicable_legs: [] }], 2)).text).toBe("1 checked bag · 23 kg");
  });
});
