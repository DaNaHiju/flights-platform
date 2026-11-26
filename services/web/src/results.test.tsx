import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ResultsList } from "./ResultsList";
import {
  activeFilterCount,
  applyFilters,
  bestScore,
  buildFacets,
  dedupe,
  NO_FILTERS,
  rankOneWay,
  rankReturn,
  sortRanked,
  timeBucket,
} from "./results";
import type { FlightOffer, RoundTripOffer } from "./types";

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

// An offer with its own local departure/arrival strings.
function at(id: string, price: number, departs: string, arrives: string, stops = 0): FlightOffer {
  const offer = o(id, price, 120, stops, id);
  offer.legs[0].departure_datetime = departs;
  offer.legs[0].arrival_datetime = arrives;
  return offer;
}

describe("sorting by time and stops", () => {
  it("orders by the LOCAL departure clock, ignoring each string's UTC offset", () => {
    // 09:00-05:00 is 14:00 UTC and 08:00+02:00 is 06:00 UTC, yet the ticket
    // shows 08:00 before 09:00: that is the order the user asked for.
    const list = [
      at("nine", 100, "2099-01-01T09:00:00-05:00", "2099-01-01T12:00:00-05:00"),
      at("eight", 100, "2099-01-01T08:00:00+02:00", "2099-01-01T10:00:00+02:00"),
      at("seven", 100, "2099-01-01T07:30:00Z", "2099-01-01T09:30:00Z"),
    ].map(rankOneWay);
    expect(ids(sortRanked(list, "departure"))).toEqual(["seven", "eight", "nine"]);
  });

  it("orders by local arrival, and a next-day arrival comes after a same-day one", () => {
    const list = [
      at("next-day", 100, "2099-01-01T23:00:00+02:00", "2099-01-02T01:00:00+02:00"),
      at("late", 100, "2099-01-01T20:00:00+02:00", "2099-01-01T23:50:00+02:00"),
      at("early", 100, "2099-01-01T06:00:00+02:00", "2099-01-01T08:00:00+02:00"),
    ].map(rankOneWay);
    expect(ids(sortRanked(list, "arrival"))).toEqual(["early", "late", "next-day"]);
  });

  it("breaks departure ties by price", () => {
    const list = [
      at("dear", 300, "2099-01-01T08:00:00+02:00", "2099-01-01T10:00:00+02:00"),
      at("cheap", 100, "2099-01-01T08:00:00+02:00", "2099-01-01T10:00:00+02:00"),
    ].map(rankOneWay);
    expect(ids(sortRanked(list, "departure"))).toEqual(["cheap", "dear"]);
  });

  it("puts offers without legs last", () => {
    const bare = { ...o("bare", 1, 60), legs: [] };
    const list = [bare, at("a", 500, "2099-01-01T08:00:00", "2099-01-01T10:00:00")].map(rankOneWay);
    expect(ids(sortRanked(list, "departure"))).toEqual(["a", "bare"]);
  });

  it("stops: fewest first, ties by price", () => {
    const list = [
      o("two", 50, 100, 2),
      o("direct-dear", 300, 100, 0),
      o("one", 80, 100, 1),
      o("direct-cheap", 200, 100, 0),
    ].map(rankOneWay);
    expect(ids(sortRanked(list, "stops"))).toEqual(["direct-cheap", "direct-dear", "one", "two"]);
  });

  it("in the return step the times are the RETURN flight's", () => {
    const pair = (id: string, back: FlightOffer): RoundTripOffer => ({
      price: 500,
      currency: "ILS",
      outbound: at(`${id}-out`, 500, "2099-01-01T23:00:00+02:00", "2099-01-02T02:00:00+01:00"),
      return: back,
    });
    const late = pair("late", at("late-back", 500, "2099-01-08T18:00:00+01:00", "2099-01-08T23:00:00+02:00"));
    const early = pair("early", at("early-back", 500, "2099-01-08T07:00:00+01:00", "2099-01-08T12:00:00+02:00"));
    const sorted = sortRanked([late, early].map(rankReturn), "departure");
    expect(sorted.map((r) => r.item.return.offer_id)).toEqual(["early-back", "late-back"]);
  });
});

// An offer with an airline, a departure hour (local), a price, hours of flying and stops.
function f(id: string, airline: string, hour: number, price: number, hours: number, stops = 0): FlightOffer {
  const offer = o(id, price, hours * 60, stops, id);
  offer.legs[0].airline = airline;
  offer.legs[0].departure_datetime = `2099-01-01T${String(hour).padStart(2, "0")}:00:00+02:00`;
  return offer;
}

const FILTERABLE = [
  f("ita-am", "ITA Airways", 7, 400, 5, 0),
  f("ita-eve", "ITA Airways", 19, 300, 9, 1),
  f("elal-pm", "El Al", 14, 500, 4, 0),
  f("tap-night", "TAP", 2, 200, 14, 2),
  f("elal-late", "El Al", 23, 450, 6, 1),
];
const visible = (filters: Parameters<typeof applyFilters>[1]) =>
  applyFilters(FILTERABLE.map(rankOneWay), filters).map((r) => r.item.offer_id);

describe("time of day buckets", () => {
  it.each([
    ["2099-01-01T00:00:00+02:00", "night"],
    ["2099-01-01T04:59:00+02:00", "night"],
    ["2099-01-01T05:00:00+02:00", "morning"],
    ["2099-01-01T11:59:00-05:00", "morning"],
    ["2099-01-01T12:00:00Z", "afternoon"],
    ["2099-01-01T17:59:00Z", "afternoon"],
    ["2099-01-01T18:00:00Z", "evening"],
    ["2099-01-01T23:59:00Z", "evening"],
  ])("%s is %s", (iso, bucket) => {
    expect(timeBucket(iso)).toBe(bucket);
  });
});

describe("filters", () => {
  it("no filter keeps everything", () => {
    expect(visible(NO_FILTERS)).toHaveLength(5);
    expect(activeFilterCount(NO_FILTERS)).toBe(0);
  });

  it("stops: nonstop / 1 / 2+, and several boxes mean either", () => {
    expect(visible({ ...NO_FILTERS, stops: ["0"] })).toEqual(["ita-am", "elal-pm"]);
    expect(visible({ ...NO_FILTERS, stops: ["1"] })).toEqual(["ita-eve", "elal-late"]);
    expect(visible({ ...NO_FILTERS, stops: ["2+"] })).toEqual(["tap-night"]);
    expect(visible({ ...NO_FILTERS, stops: ["0", "2+"] })).toEqual(["ita-am", "elal-pm", "tap-night"]);
  });

  it("airlines: an offer passes when any of its airlines is ticked", () => {
    expect(visible({ ...NO_FILTERS, airlines: ["El Al"] })).toEqual(["elal-pm", "elal-late"]);
    const mixed = f("mixed", "Lufthansa", 9, 100, 5, 1);
    mixed.legs.push({ ...mixed.legs[0], airline: "Swiss", flight_number: "LX1" });
    const ranked = [rankOneWay(mixed)];
    expect(applyFilters(ranked, { ...NO_FILTERS, airlines: ["Swiss"] })).toHaveLength(1);
    expect(applyFilters(ranked, { ...NO_FILTERS, airlines: ["TAP"] })).toHaveLength(0);
  });

  it("departure time uses the local hour of the string", () => {
    expect(visible({ ...NO_FILTERS, times: ["morning"] })).toEqual(["ita-am"]);
    expect(visible({ ...NO_FILTERS, times: ["night", "evening"] })).toEqual(["ita-eve", "tap-night", "elal-late"]);
  });

  it("max price and max duration are inclusive upper bounds", () => {
    expect(visible({ ...NO_FILTERS, maxPrice: 400 })).toEqual(["ita-am", "ita-eve", "tap-night"]);
    expect(visible({ ...NO_FILTERS, maxDurationHours: 6 })).toEqual(["ita-am", "elal-pm", "elal-late"]);
  });

  it("different groups must all match", () => {
    const filters = { ...NO_FILTERS, airlines: ["El Al"], stops: ["0" as const], maxPrice: 450 };
    expect(visible(filters)).toEqual([]);
    expect(activeFilterCount(filters)).toBe(3);
    expect(visible({ ...filters, maxPrice: 500 })).toEqual(["elal-pm"]);
  });

  it("an offer without legs fails a departure-time filter instead of crashing", () => {
    const bare = rankOneWay({ ...o("bare", 1, 60), legs: [] });
    expect(applyFilters([bare], { ...NO_FILTERS, times: ["morning"] })).toHaveLength(0);
    expect(applyFilters([bare], NO_FILTERS)).toHaveLength(1);
  });

  it("facets: counts, airlines and ranges rounded outwards", () => {
    const facets = buildFacets(FILTERABLE.map(rankOneWay));
    expect(facets.stopCounts).toEqual({ "0": 2, "1": 2, "2+": 1 });
    expect(facets.airlines).toEqual(["El Al", "ITA Airways", "TAP"]);
    expect([facets.minPrice, facets.maxPrice]).toEqual([200, 500]);
    expect([facets.minHours, facets.maxHours]).toEqual([4, 14]);
    expect(facets.currency).toBe("ILS");
  });
});

describe("filters in a round trip", () => {
  it("the return step filters by the RETURN flight's airline and departure hour", () => {
    const pair = (id: string, outAirline: string, backAirline: string, backHour: number): RoundTripOffer => ({
      price: 900,
      currency: "ILS",
      outbound: f(`${id}-out`, outAirline, 8, 900, 5),
      return: f(`${id}-back`, backAirline, backHour, 900, 5),
    });
    const pairs = [pair("a", "El Al", "TAP", 7), pair("b", "TAP", "El Al", 20)].map(rankReturn);
    const backs = (filters: Parameters<typeof applyFilters>[1]) =>
      applyFilters(pairs, filters).map((r) => r.item.return.offer_id);
    expect(backs({ ...NO_FILTERS, airlines: ["TAP"] })).toEqual(["a-back"]);
    expect(backs({ ...NO_FILTERS, times: ["evening"] })).toEqual(["b-back"]);
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

  it("the Sort by menu lists the six criteria and shares its state with the tabs", () => {
    list([o("slow-cheap", 100, 600), o("fast-dear", 300, 100), o("balanced", 150, 150)]);
    const menu = screen.getByRole("combobox", { name: "Sort by" }) as HTMLSelectElement;
    expect(within(menu).getAllByRole("option").map((x) => x.textContent)).toEqual([
      "Best",
      "Price",
      "Duration",
      "Departure time",
      "Arrival time",
      "Stops",
    ]);
    expect(menu.value).toBe("best");

    fireEvent.change(menu, { target: { value: "cheapest" } });
    expect(screen.getAllByRole("listitem")[0].textContent).toBe("slow-cheap");
    expect(screen.getByRole("button", { name: /Cheapest/ }).getAttribute("aria-pressed")).toBe("true");

    // The other way round: a tab moves the menu.
    fireEvent.click(screen.getByRole("button", { name: /Fastest/ }));
    expect(menu.value).toBe("fastest");
    expect(screen.getAllByRole("listitem")[0].textContent).toBe("fast-dear");
  });

  it("Departure time leaves every tab unpressed and keeps Show more working", () => {
    const offers = Array.from({ length: 25 }, (_, i) =>
      at(`o${i}`, 100 + i, `2099-01-01T${String(23 - (i % 24)).padStart(2, "0")}:00:00+02:00`, "2099-01-02T03:00:00+02:00"),
    );
    list(offers);
    fireEvent.change(screen.getByRole("combobox", { name: "Sort by" }), { target: { value: "departure" } });
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
  });

  describe("filters panel", () => {
    const panel = () => within(screen.getByRole("complementary", { name: "Filters" }));
    const rowIds = () => screen.getAllByRole("listitem").map((li) => li.textContent);

    it("shows Stops with a count per option and the airlines that appear", () => {
      list(FILTERABLE);
      expect(panel().getByRole("checkbox", { name: /Nonstop/ }).closest("label")!.textContent).toContain("2");
      expect(panel().getByRole("checkbox", { name: /1 stop/ }).closest("label")!.textContent).toContain("2");
      expect(panel().getByRole("checkbox", { name: /2\+ stops/ }).closest("label")!.textContent).toContain("1");
      for (const name of ["El Al", "ITA Airways", "TAP"]) {
        expect(panel().getByRole("checkbox", { name })).toBeTruthy();
      }
      expect(panel().getByText("Showing 5 of 5")).toBeTruthy();
    });

    it("ticking a box narrows the list and updates Showing N of M and the count", () => {
      list(FILTERABLE);
      fireEvent.click(panel().getByRole("checkbox", { name: "El Al" }));
      expect(rowIds().sort()).toEqual(["elal-late", "elal-pm"]);
      expect(panel().getByText("Showing 2 of 5")).toBeTruthy();
      expect(screen.getByText("2 results")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Filters (1)" })).toBeTruthy();
    });

    it("the tabs and Sort by work on the filtered list", () => {
      list(FILTERABLE);
      fireEvent.click(panel().getByRole("checkbox", { name: /Nonstop/ }));
      // Nonstop: ita-am (400) and elal-pm (500). Cheapest leads with 400.
      expect(screen.getByRole("button", { name: /Cheapest/ }).textContent).toContain("₪400");
      fireEvent.change(screen.getByRole("combobox", { name: "Sort by" }), { target: { value: "departure" } });
      expect(rowIds()).toEqual(["ita-am", "elal-pm"]);
    });

    it("the price slider filters, and dragging it back to the end removes the limit", () => {
      list(FILTERABLE);
      const slider = panel().getByRole("slider", { name: /Max price/ });
      fireEvent.change(slider, { target: { value: "300" } });
      expect(rowIds().sort()).toEqual(["ita-eve", "tap-night"]);
      fireEvent.change(slider, { target: { value: "500" } });
      expect(rowIds()).toHaveLength(5);
      expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
    });

    it("the duration slider is in hours", () => {
      list(FILTERABLE);
      fireEvent.change(panel().getByRole("slider", { name: /Max duration/ }), { target: { value: "5" } });
      expect(rowIds().sort()).toEqual(["elal-pm", "ita-am"]);
    });

    it("0 results shows a message and a Clear button that restores the list", () => {
      list(FILTERABLE);
      fireEvent.click(panel().getByRole("checkbox", { name: "TAP" }));
      fireEvent.click(panel().getByRole("checkbox", { name: /Nonstop/ }));
      expect(screen.getByText("No flights match your filters.")).toBeTruthy();
      expect(screen.queryByRole("group", { name: /Sort/ })).toBeNull();
      expect(panel().getByText("Showing 0 of 5")).toBeTruthy();

      const clears = screen.getAllByRole("button", { name: "Clear filters" });
      fireEvent.click(clears[clears.length - 1]);
      expect(rowIds()).toHaveLength(5);
      expect(screen.queryByText("No flights match your filters.")).toBeNull();
    });

    it("Clear filters is disabled until something is filtered", () => {
      list(FILTERABLE);
      const clear = panel().getByRole("button", { name: "Clear filters" }) as HTMLButtonElement;
      expect(clear.disabled).toBe(true);
      fireEvent.click(panel().getByRole("checkbox", { name: "TAP" }));
      expect(clear.disabled).toBe(false);
    });

    it("changing a filter goes back to the first page of Show more", () => {
      const offers = Array.from({ length: 25 }, (_, i) => f(`n${i}`, i % 2 ? "El Al" : "TAP", 9, 100 + i, 5));
      list(offers);
      fireEvent.click(screen.getByRole("button", { name: "Show more" }));
      expect(screen.getAllByRole("listitem")).toHaveLength(20);
      fireEvent.click(panel().getByRole("checkbox", { name: "TAP" }));
      expect(screen.getAllByRole("listitem")).toHaveLength(10);
      fireEvent.click(screen.getByRole("button", { name: "Show more" }));
      expect(screen.getAllByRole("listitem")).toHaveLength(13);
    });

    it("the Filters button opens the panel on a phone (aria-expanded)", () => {
      list(FILTERABLE);
      const button = screen.getByRole("button", { name: "Filters" });
      expect(button.getAttribute("aria-expanded")).toBe("false");
      fireEvent.click(button);
      expect(button.getAttribute("aria-expanded")).toBe("true");
      expect(panel()).toBeTruthy();
      expect(screen.getByRole("complementary", { name: "Filters" }).className).toContain("open");
    });
  });
});
