import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ResultsList } from "./ResultsList";
import { bestScore, dedupe, rankOneWay, sortRanked } from "./results";
import type { FlightOffer } from "./types";

afterEach(cleanup);

function o(id: string, price: number, minutes: number, stops = 0, flight = id): FlightOffer {
  return {
    offer_id: id,
    price,
    currency: "ILS",
    duration_minutes: minutes,
    stops,
    primary_airline: "X",
    legs: [
      {
        airline: "X",
        flight_number: flight,
        departure_airport: "A",
        arrival_airport: "B",
        departure_datetime: "2099-01-01T08:00:00",
        arrival_datetime: "2099-01-01T10:00:00",
        duration_minutes: minutes,
      },
    ],
  };
}

const ids = (list: { item: FlightOffer }[]) => list.map((r) => r.item.offer_id);

describe("dedupe", () => {
  it("keeps only the cheapest of offers with the same flights", () => {
    const list = [o("dear", 500, 120, 0, "LY1"), o("cheap", 400, 120, 0, "LY1"), o("other", 450, 120, 0, "LY2")];
    expect(ids(dedupe(list.map(rankOneWay)))).toEqual(["cheap", "other"]);
  });

  it("treats a different departure time as a different flight", () => {
    const later = o("later", 300, 120, 0, "LY1");
    later.legs[0].departure_datetime = "2099-01-01T09:00:00";
    expect(dedupe([o("a", 400, 120, 0, "LY1"), later].map(rankOneWay))).toHaveLength(2);
  });

  it("never merges offers that have no legs to compare", () => {
    const bare = (id: string) => ({ ...o(id, 100, 60), legs: [] });
    expect(dedupe([bare("a"), bare("b")].map(rankOneWay))).toHaveLength(2);
  });
});

describe("sorting", () => {
  const list = [
    o("slow-cheap", 100, 600, 1),
    o("fast-dear", 300, 100, 0),
    o("balanced", 150, 150, 0),
  ].map(rankOneWay);

  it("cheapest orders by price, fastest by total duration", () => {
    expect(ids(sortRanked(list, "cheapest"))).toEqual(["slow-cheap", "balanced", "fast-dear"]);
    expect(ids(sortRanked(list, "fastest"))).toEqual(["fast-dear", "balanced", "slow-cheap"]);
  });

  it("best is price/minPrice + duration/minDuration + 0.25 per stop", () => {
    // min price 100, min duration 100
    expect(bestScore(list[0], 100, 100)).toBeCloseTo(1 + 6 + 0.25);
    expect(bestScore(list[1], 100, 100)).toBeCloseTo(3 + 1);
    expect(bestScore(list[2], 100, 100)).toBeCloseTo(1.5 + 1.5);
    expect(ids(sortRanked(list, "best"))).toEqual(["balanced", "fast-dear", "slow-cheap"]);
  });

  it("does not mutate the input", () => {
    const before = ids(list);
    sortRanked(list, "cheapest");
    expect(ids(list)).toEqual(before);
  });
});

describe("ResultsList", () => {
  function many(n: number): FlightOffer[] {
    return Array.from({ length: n }, (_, i) => o(`o${i}`, 1000 - i, 100 + i, 0, `F${i}`));
  }

  function list(offers: FlightOffer[]) {
    render(
      <ResultsList
        results={offers.map(rankOneWay)}
        renderRow={(offer) => <li>{offer.offer_id}</li>}
      />,
    );
  }

  it("shows 10 rows, the count, and 10 more per Show more", () => {
    list(many(25));
    expect(screen.getByText("25 results")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(25);
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("has no Show more for a short list and counts after removing duplicates", () => {
    list([o("a", 10, 60, 0, "S"), o("b", 20, 60, 0, "S")]);
    expect(screen.getByText("1 result")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("each tab shows the price leading its view and reorders the rows", () => {
    list([o("slow-cheap", 100, 600), o("fast-dear", 300, 100), o("balanced", 150, 150)]);
    const tabs = within(screen.getByRole("group", { name: /Sort/ }));
    expect(tabs.getByRole("button", { name: /Cheapest/ }).textContent).toContain("₪100");
    expect(tabs.getByRole("button", { name: /Fastest/ }).textContent).toContain("₪300");
    expect(tabs.getByRole("button", { name: /Best/ }).textContent).toContain("₪150");

    expect(screen.getAllByRole("listitem")[0].textContent).toBe("balanced");
    fireEvent.click(tabs.getByRole("button", { name: /Cheapest/ }));
    expect(screen.getAllByRole("listitem")[0].textContent).toBe("slow-cheap");
    fireEvent.click(tabs.getByRole("button", { name: /Fastest/ }));
    expect(screen.getAllByRole("listitem")[0].textContent).toBe("fast-dear");
  });
});
