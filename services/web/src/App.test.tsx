/// <reference types="vite/client" />
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { PROVIDER_DOWN_MESSAGE } from "./api";
import { airlineUrl } from "./airlines";
import { resolveCode } from "./AirportInput";
import { SearchForm } from "./SearchForm";
import { DealItem } from "./DealItem";
import {
  countryName,
  dayDifference,
  formatDuration,
  formatPrice,
  formatDay,
  localTime,
  minutesBetween,
  placeLabel,
} from "./format";
import type { Deal, FlightOffer, Leg } from "./types";

function offer(
  id: string,
  price: number,
  airline: string,
  code: string | null = null,
  deepLink: string | null = null,
): FlightOffer {
  return {
    offer_id: id,
    price,
    currency: "USD",
    duration_minutes: 200,
    stops: 0,
    primary_airline: airline,
    primary_airline_code: code,
    deep_link: deepLink,
    legs: [],
  };
}

// Answers by query string: each entry is [url fragment, status, body].
function mockFetch(routes: [string, number, unknown][]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.startsWith("/api/deals")) {
        return Promise.resolve(new Response(JSON.stringify({ deals: [] })));
      }
      const [, status, body] = routes.find(([fragment]) => url.includes(fragment)) ?? [
        "",
        404,
        {},
      ];
      return Promise.resolve(new Response(JSON.stringify(body), { status }));
    }),
  );
}

// The trip type is a group of toggle buttons (tabs), not a select.
function pickTrip(name: string) {
  fireEvent.click(within(screen.getByLabelText("Trip type")).getByRole("button", { name }));
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

// The rows of a result list (the sort tabs also show prices, so scope to the list).
function rows(name = "Flight results") {
  return within(screen.getByRole("list", { name }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SearchForm", () => {
  it("renders origin, destination and date fields and a submit button", () => {
    render(<SearchForm onSearch={() => {}} disabled={false} />);

    expect(screen.getByLabelText("Origin")).toBeTruthy();
    expect(screen.getByLabelText("Destination")).toBeTruthy();
    expect(screen.getByLabelText("Date")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Search" })).toBeTruthy();
  });

  it("offers the three trip types and shows the extra fields of each", () => {
    render(<SearchForm onSearch={() => {}} disabled={false} />);

    const tabs = within(screen.getByLabelText("Trip type")).getAllByRole("button");
    expect(tabs.map((t) => t.textContent)).toEqual(["One way", "Round trip", "Multi-city"]);
    expect(tabs[0].getAttribute("aria-pressed")).toBe("true");

    expect(screen.queryByLabelText("Return")).toBeNull();
    pickTrip("Round trip");
    expect(screen.getByLabelText("Return")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Round trip" }).getAttribute("aria-pressed")).toBe("true");

    pickTrip("Multi-city");
    expect(screen.queryByLabelText("Return")).toBeNull();
    expect(screen.getByLabelText("Origin 2")).toBeTruthy();
    expect(screen.getByLabelText("Destination 2")).toBeTruthy();
    expect(screen.getByLabelText("Date 2")).toBeTruthy();
  });
});

describe("App", () => {
  it("shows the provider-down message when the API answers 502", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve(
          url.startsWith("/api/deals")
            ? new Response(JSON.stringify({ deals: [] }), { status: 200 })
            : new Response(JSON.stringify({ error: "provider_unavailable" }), {
                status: 502,
              }),
        ),
      ),
    );

    render(<App />);
    fireEvent.change(screen.getByLabelText("Origin"), { target: { value: "eze" } });
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "mad" } });
    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2099-01-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(PROVIDER_DOWN_MESSAGE),
    );
  });
});

// A one-way offer with one real flight, so it can be told apart and grouped.
function flight(id: string, price: number, number: string, hour: string, over: Partial<Leg> = {}): FlightOffer {
  return {
    ...offer(id, price, "El Al", "LY"),
    legs: [
      leg({
        flight_number: number,
        airline_code: "LY",
        departure_datetime: `2099-01-01T${hour}:00:00+02:00`,
        arrival_datetime: `2099-01-01T${String(+hour.slice(0, 2) + 3).padStart(2, "0")}:00:00+01:00`,
        ...over,
      }),
    ],
  };
}

function pair(out: FlightOffer, back: FlightOffer, price: number, deepLink = "https://book.example/pair") {
  return { price, currency: "USD", deep_link: deepLink, outbound: out, return: back };
}

// Book / Go to links; the header and footer have links of their own.
const BOOKING = /^(Book|Go to)/;

function chooseRow(index: number, name = "Flight results") {
  fireEvent.click(rows(name).getAllByRole("button", { name: "Choose" })[index]);
}

function stepItem(label: string) {
  return within(screen.getByRole("list", { name: "Steps" })).getByText(label).closest("li")!;
}

async function searchRoundTrip(results: unknown[]) {
  mockFetch([["return_date=2099-01-08", 200, { results }]]);
  render(<App />);
  pickTrip("Round trip");
  type("Origin", "tlv");
  type("Destination", "ath");
  type("Date", "2099-01-01");
  type("Return", "2099-01-08");
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(screen.getByRole("list", { name: "Outbound flights" })).toBeTruthy());
}

async function searchMultiCity(routes: [string, number, unknown][]) {
  mockFetch(routes);
  render(<App />);
  pickTrip("Multi-city");
  type("Origin", "tlv");
  type("Destination", "ath");
  type("Date", "2099-01-01");
  type("Origin 2", "ath");
  type("Destination 2", "tlv");
  type("Date 2", "2099-01-08");
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

describe("round trip steps", () => {
  const out1 = flight("o1", 0, "LY1", "08");
  const out2 = flight("o2", 0, "LY2", "13");
  const back1 = flight("r1", 0, "LY11", "09");
  const back2 = flight("r2", 0, "LY12", "15");
  const back3 = flight("r3", 0, "LY13", "18");
  // two pairs share outbound LY1; a third pair has its own outbound
  const results = [
    pair(out1, back2, 1000, "https://book.example/b"),
    pair(out1, back1, 900, "https://book.example/a"),
    pair(out2, back3, 1200),
  ];

  it("groups the pairs by outbound: one row, the lowest price, N return options", async () => {
    await searchRoundTrip(results);
    const list = rows("Outbound flights");
    expect(list.getAllByRole("button", { name: "Choose" })).toHaveLength(2);
    expect(list.getByText("2 return options")).toBeTruthy();
    expect(list.getByText("1 return option")).toBeTruthy();
    expect(list.getByText("$900")).toBeTruthy();
    expect(list.queryByText("$1,000")).toBeNull();
    expect(list.getAllByText("from")).toHaveLength(2);
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);
  });

  it("shows only the returns sold with the chosen outbound, each with the trip total", async () => {
    await searchRoundTrip(results);
    // best order puts the cheapest group (LY1) first
    chooseRow(0, "Outbound flights");

    const list = rows("Return flights");
    expect(list.getAllByRole("button", { name: "Choose" })).toHaveLength(2);
    expect(list.getByText("$900")).toBeTruthy();
    expect(list.getByText("$1,000")).toBeTruthy();
    expect(list.queryByText("$1,200")).toBeNull();
    // sort tabs and paging still work in this step
    expect(screen.getByRole("group", { name: "Sort Return flights" })).toBeTruthy();
    expect(screen.getByText("2 results")).toBeTruthy();
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);
  });

  it("reviews the whole trip with the pair's total, Book and Go to only there", async () => {
    await searchRoundTrip(results);
    chooseRow(0, "Outbound flights");
    // the 15:00 return is the $1,000 pair, whose deep link is /b
    fireEvent.click(
      within(rows("Return flights").getByText(/15:00/).closest("li")!).getByRole("button", {
        name: "Choose",
      }),
    );

    const trip = within(screen.getByRole("list", { name: "Your trip" }));
    expect(trip.getByText("$1,000")).toBeTruthy();
    expect(trip.getByText("round trip")).toBeTruthy();
    expect(trip.getAllByText(/layover|LY1|El Al/).length).toBeGreaterThan(0);
    expect(trip.getAllByText("Outbound").length).toBeGreaterThan(0);
    expect(trip.getAllByText("Return").length).toBeGreaterThan(0);
    expect(trip.getByRole("link", { name: "Book" }).getAttribute("href")).toBe(
      "https://book.example/b",
    );
    expect(trip.getByRole("link", { name: "Go to El Al" })).toBeTruthy();
    expect(stepItem("Outbound").textContent).toContain("Change");
    expect(stepItem("Return").textContent).toContain("Change");
  });

  it("Change goes back to that step and forgets the later choices", async () => {
    await searchRoundTrip(results);
    chooseRow(0, "Outbound flights");
    chooseRow(0, "Return flights");
    expect(screen.getByRole("list", { name: "Your trip" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Change Return" }));
    expect(screen.queryByRole("list", { name: "Your trip" })).toBeNull();
    expect(rows("Return flights").getAllByRole("button", { name: "Choose" })).toHaveLength(2);
    expect(stepItem("Outbound").textContent).toContain("Change");
    expect(stepItem("Return").textContent).not.toContain("Change");

    fireEvent.click(screen.getByRole("button", { name: "Change Outbound" }));
    expect(rows("Outbound flights").getAllByRole("button", { name: "Choose" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /^Change/ })).toBeNull();
  });
});

describe("multi-city steps", () => {
  const routes: [string, number, unknown][] = [
    ["origin=TLV", 200, { results: [flight("a", 150, "LY1", "08"), flight("b", 90, "FR1", "10")] }],
    ["origin=ATH", 200, { results: [{ ...flight("c", 70, "A31", "09"), deep_link: "https://book.example/c" }] }],
  ];

  it("picks one flight per leg and reviews two tickets, each with its own Book", async () => {
    await searchMultiCity(routes);
    await waitFor(() => expect(screen.getByText(/Leg 1: TLV → ATH/)).toBeTruthy());
    expect(screen.queryByText(/Leg 2/)).toBeNull();
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);

    chooseRow(0, "Flights, leg 1");
    expect(screen.getByText(/Leg 2: ATH → TLV/)).toBeTruthy();
    chooseRow(0, "Flights, leg 2");

    expect(screen.getByText("2 tickets")).toBeTruthy();
    // 90 + 70 (the best-ranked flight of leg 1 is the cheap, short one)
    expect(screen.getByText(/Total: \$160/)).toBeTruthy();
    expect(
      screen.getByText("Separate bookings: if flight 1 is delayed, airline 2 won't wait for you."),
    ).toBeTruthy();
    expect(screen.getByRole("list", { name: "Ticket 1" })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Ticket 2" })).toBeTruthy();
    // ticket 1 has no deep link in the mock, so only ticket 2 can be booked
    expect(screen.queryByRole("link", { name: "Book ticket 1" })).toBeNull();
    expect(
      screen.getByRole("link", { name: "Book ticket 2" }).getAttribute("href"),
    ).toBe("https://book.example/c");
  });

  it("offers a Book per ticket when both have a deep link", async () => {
    const withLinks: [string, number, unknown][] = [
      ["origin=TLV", 200, { results: [{ ...flight("a", 150, "LY1", "08"), deep_link: "https://book.example/a" }] }],
      routes[1],
    ];
    await searchMultiCity(withLinks);
    await waitFor(() => expect(screen.getByText(/Leg 1/)).toBeTruthy());
    chooseRow(0, "Flights, leg 1");
    chooseRow(0, "Flights, leg 2");
    expect(screen.getByRole("link", { name: "Book ticket 1" }).getAttribute("href")).toBe(
      "https://book.example/a",
    );
    expect(screen.getByRole("link", { name: "Book ticket 2" })).toBeTruthy();
    expect(screen.getByText(/Total: \$220/)).toBeTruthy();
  });

  it("shows a failed leg's error at its own step", async () => {
    await searchMultiCity([
      routes[0],
      ["origin=ATH", 502, { error: "provider_unavailable" }],
    ]);
    await waitFor(() => expect(screen.getByText(/Leg 1: TLV → ATH/)).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
    chooseRow(0, "Flights, leg 1");
    expect(screen.getByRole("alert").textContent).toBe(PROVIDER_DOWN_MESSAGE);
    expect(screen.getByText(/Leg 2: ATH → TLV/)).toBeTruthy();
  });
});

describe("one way steps", () => {
  async function searchOneWay(offers: FlightOffer[]) {
    mockFetch([["origin=TLV", 200, { results: offers }]]);
    render(<App />);
    type("Origin", "tlv");
    type("Destination", "ath");
    type("Date", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(rows().getAllByRole("button", { name: "Choose" }).length).toBeGreaterThan(0));
  }

  it("goes Choose -> Review, and only Review has Book and Go to", async () => {
    await searchOneWay([{ ...flight("a", 100, "LY1", "08"), deep_link: "https://airline.example/deep?x=1" }]);
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);
    fireEvent.click(rows().getByRole("button", { name: /\$100/ }));
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);

    chooseRow(0);
    const review = within(screen.getByRole("list", { name: "Your flight" }));
    const book = review.getByRole("link", { name: "Book" });
    expect(book.getAttribute("href")).toBe("https://airline.example/deep?x=1");
    expect(book.getAttribute("target")).toBe("_blank");
    expect(book.getAttribute("rel")).toBe("noopener noreferrer");
    const airline = review.getByRole("link", { name: "Go to El Al" });
    expect(airline.getAttribute("href")).toBe(airlineUrl("LY"));
    expect(airline.getAttribute("rel")).toBe("noopener noreferrer");
    expect(stepItem("Flight").textContent).toContain("Change");
  });

  it("has no Book without a deep link, and no Go to for an unmapped airline", async () => {
    await searchOneWay([flight("a", 100, "ZZ1", "08", { airline_code: "ZZ" })]);
    chooseRow(0);
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);
    expect(airlineUrl(null)).toBeUndefined();
  });

  it("a new search starts over at the first step", async () => {
    await searchOneWay([flight("a", 100, "LY1", "08")]);
    chooseRow(0);
    expect(screen.getByRole("list", { name: "Your flight" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(rows().getAllByRole("button", { name: "Choose" })).toHaveLength(1));
    expect(screen.queryByRole("list", { name: "Your flight" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Change/ })).toBeNull();
  });
});

function leg(over: Partial<Leg> = {}): Leg {
  return {
    airline: "El Al",
    flight_number: "LY381",
    departure_airport: "Ben Gurion International Airport",
    arrival_airport: "Leonardo Da Vinci (Fiumicino) International Airport",
    departure_datetime: "2099-01-01T08:00:00",
    arrival_datetime: "2099-01-01T11:00:00",
    duration_minutes: 380,
    departure_airport_code: "TLV",
    arrival_airport_code: "FCO",
    departure_city: "Tel Aviv",
    arrival_city: "Rome",
    departure_country_code: "IL",
    arrival_country_code: "IT",
    ...over,
  };
}

describe("formatting", () => {
  it("formats durations as 6h 20m", () => {
    expect(formatDuration(380)).toBe("6h 20m");
    expect(formatDuration(360)).toBe("6h");
    expect(formatDuration(45)).toBe("45m");
  });

  it("renders City, Country (IATA) and falls back to the airport name", () => {
    expect(countryName("IT")).toBe("Italy");
    expect(
      placeLabel({ code: "FCO", city: "Rome", countryCode: "IT", airportName: "Fiumicino" }),
    ).toBe("Rome, Italy (FCO)");
    expect(placeLabel({ code: "PBI", city: null, countryCode: null, airportName: "Palm Beach" })).toBe(
      "Palm Beach",
    );
    expect(placeLabel({})).toBe("");
  });
});

async function searchOne(offers: unknown[]) {
  mockFetch([["origin=TLV", 200, { results: offers }]]);
  render(<App />);
  type("Origin", "tlv");
  type("Destination", "fco");
  type("Date", "2099-01-01");
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(rows().getAllByRole("button").length).toBeGreaterThan(0));
}

describe("offer details", () => {
  it("shows a compact line first and the timeline once the row is clicked", async () => {
    await searchOne([{ ...offer("a", 100, "El Al"), duration_minutes: 380, legs: [leg()] }]);

    // closed: airline, local times, duration, codes, nonstop, price and trip kind
    expect(rows().getByText("El Al")).toBeTruthy();
    expect(screen.getByText(/08:00 → 11:00/)).toBeTruthy();
    expect(screen.getByText("6h 20m")).toBeTruthy();
    // scoped to the list: the Stops filter has a "Nonstop" option too
    expect(rows().getByText("Nonstop")).toBeTruthy();
    expect(rows().getByText("one way")).toBeTruthy();
    expect(screen.queryByText(/Ben Gurion International Airport/)).toBeNull();

    fireEvent.click(rows().getByRole("button", { name: /\$100/ }));
    expect(screen.getByText(/Ben Gurion International Airport \(TLV\)/)).toBeTruthy();
    expect(screen.getByText(/Fiumicino\) International Airport \(FCO\)/)).toBeTruthy();
    expect(screen.getByText(/6h 20m · El Al LY381/)).toBeTruthy();
  });

  it("still renders an old offer whose legs lack the added fields", async () => {
    const old = leg();
    for (const key of Object.keys(old).filter((k) => /code|city/.test(k))) {
      delete (old as unknown as Record<string, unknown>)[key];
    }
    await searchOne([{ ...offer("a", 100, "El Al"), legs: [old] }]);
    fireEvent.click(rows().getByRole("button", { name: /\$100/ }));
    expect(screen.getByText(/Ben Gurion International Airport/)).toBeTruthy();
    expect(screen.getByText(/3h 20m/)).toBeTruthy();
  });
});

describe("deals", () => {
  const base: Deal = {
    destination: "FCO",
    departure_date: "2099-02-01",
    price: 120,
    currency: "USD",
    airline: "ITA Airways",
  };
  const full: Deal = {
    ...base,
    origin: "TLV",
    origin_city: "Tel Aviv",
    origin_country_code: "IL",
    origin_airport_name: "Ben Gurion International Airport",
    destination_city: "Rome",
    destination_country_code: "IT",
    destination_airport_name: "Fiumicino",
    total_duration_minutes: 260,
  };

  it("shows city and country, the from price, and origin → destination", () => {
    render(
      <ul>
        <DealItem deal={full} />
      </ul>,
    );
    expect(screen.getByText("Rome, Italy")).toBeTruthy();
    expect(screen.getByText("$120")).toBeTruthy();
    expect(screen.getByText("from")).toBeTruthy();
    expect(screen.getByText(/Tel Aviv, Israel \(TLV\) → Rome, Italy \(FCO\)/)).toBeTruthy();
    expect(screen.getByText(/Ben Gurion International Airport → Fiumicino/)).toBeTruthy();
    expect(screen.getByText(/ITA Airways · 4h 20m/)).toBeTruthy();
  });

  it("a round-trip deal shows both dates and 'from X · round trip'", () => {
    render(
      <ul>
        <DealItem deal={{ ...full, departure_date: "2099-01-12", return_date: "2099-01-19" }} />
      </ul>,
    );
    expect(screen.getByText(/^12 Jan – 19 Jan · ITA Airways · 4h 20m$/)).toBeTruthy();
    expect(screen.getByText("$120").textContent).toContain("from");
    expect(screen.getByText("· round trip")).toBeTruthy();
    expect(screen.queryByText("· one way")).toBeNull();
  });

  it("a deal without return_date is one way, with a single date", () => {
    render(
      <ul>
        <DealItem deal={{ ...full, departure_date: "2099-01-12" }} />
      </ul>,
    );
    expect(screen.getByText(/^12 Jan · ITA Airways/)).toBeTruthy();
    expect(screen.getByText("· one way")).toBeTruthy();
    expect(screen.queryByText("· round trip")).toBeNull();
  });

  it("a null return_date is also one way", () => {
    render(
      <ul>
        <DealItem deal={{ ...full, return_date: null }} />
      </ul>,
    );
    expect(screen.getByText("· one way")).toBeTruthy();
  });

  it("tolerates a deal cached without the added fields", () => {
    render(
      <ul>
        <DealItem deal={base} onSeeFlights={() => {}} />
      </ul>,
    );
    expect(screen.getByText("FCO")).toBeTruthy();
    expect(screen.getByText("$120")).toBeTruthy();
    // no origin to fill the form with: no button
    expect(screen.queryByRole("button", { name: /See flights/ })).toBeNull();
  });

  it("uses the destination photo, lazy, with a descriptive alt, and has no booking link", () => {
    render(
      <ul>
        <DealItem deal={full} onSeeFlights={() => {}} />
      </ul>,
    );
    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe("/destinations/FCO.webp");
    expect(img.getAttribute("alt")).toBe("View of Rome, Italy");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(screen.queryAllByRole("link", { name: BOOKING })).toHaveLength(0);

    // a missing photo leaves the gradient, without a broken image
    fireEvent.error(img);
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("See flights fills the form as a one-way search and runs it live", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.startsWith("/api/deals")) {
          return Promise.resolve(new Response(JSON.stringify({ deals: [full] })));
        }
        if (url.startsWith("/api/flights")) {
          return Promise.resolve(
            new Response(JSON.stringify({ results: [offer("a", 99, "ITA Airways")] })),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({ results: [] })));
      }),
    );
    render(<App />);
    pickTrip("Round trip");
    fireEvent.click(await screen.findByRole("button", { name: "See flights to Rome, Italy" }));

    await waitFor(() => expect(rows().getByText("$99")).toBeTruthy());
    expect((screen.getByLabelText("Origin") as HTMLInputElement).value).toBe("TLV");
    expect((screen.getByLabelText("Destination") as HTMLInputElement).value).toBe("FCO");
    expect((screen.getByLabelText("Date") as HTMLInputElement).value).toBe("2099-02-01");
    expect(screen.queryByLabelText("Return")).toBeNull();
    const searched = (fetch as ReturnType<typeof vi.fn>).mock.calls
      .map(([u]) => u as string)
      .find((u) => u.startsWith("/api/flights"));
    expect(searched).toBe("/api/flights?origin=TLV&destination=FCO&date=2099-02-01");
  });

  it("See flights on a round-trip deal opens Round trip with both dates and searches the pair", async () => {
    const roundTrip: Deal = { ...full, departure_date: "2099-02-01", return_date: "2099-02-08" };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.startsWith("/api/deals")) {
          return Promise.resolve(new Response(JSON.stringify({ deals: [roundTrip] })));
        }
        return Promise.resolve(new Response(JSON.stringify({ results: [] })));
      }),
    );
    render(<App />);
    // The form starts in One way: the deal must switch it.
    expect(
      within(screen.getByLabelText("Trip type")).getByRole("button", { name: "One way" }).getAttribute("aria-pressed"),
    ).toBe("true");
    fireEvent.click(await screen.findByRole("button", { name: "See flights to Rome, Italy" }));

    await waitFor(() =>
      expect(
        within(screen.getByLabelText("Trip type"))
          .getByRole("button", { name: "Round trip" })
          .getAttribute("aria-pressed"),
      ).toBe("true"),
    );
    expect((screen.getByLabelText("Date") as HTMLInputElement).value).toBe("2099-02-01");
    expect((screen.getByLabelText("Return") as HTMLInputElement).value).toBe("2099-02-08");
    const searched = (fetch as ReturnType<typeof vi.fn>).mock.calls
      .map(([u]) => u as string)
      .find((u) => u.startsWith("/api/flights"));
    expect(searched).toBe("/api/flights?origin=TLV&destination=FCO&date=2099-02-01&return_date=2099-02-08");
  });
});

describe("formatDay", () => {
  it("writes a calendar date as day and short month, without touching timezones", () => {
    expect(formatDay("2099-01-12")).toBe("12 Jan");
    expect(formatDay("2099-12-01")).toBe("1 Dec");
    expect(formatDay("2099-03-31")).toBe("31 Mar");
  });
});

describe("language", () => {
  it("has no Spanish strings in src (outside this test)", async () => {
    const files = import.meta.glob("./*.{ts,tsx}", { query: "?raw", import: "default", eager: true });
    const spanish = /\b(Buscar|Origen|Destino|Fecha|Vuelta|Reservar|Ir a|escala|directo|Tramo|Ofertas|Cargando|Algo salió|Ida y vuelta|Probá|Usá)\b/;
    for (const [name, source] of Object.entries(files)) {
      if (name.endsWith(".test.tsx")) continue;
      expect(spanish.test(source as string), name).toBe(false);
    }
  });
});

describe("airport typeahead", () => {
  const madrid = [
    {
      id: "CMAD",
      iata_code: "MAD",
      sub_type: "CITY",
      name: "Madrid",
      city_name: "Madrid",
      country_name: "Spain",
      search_code: "MAD",
    },
    {
      id: "AMAD",
      iata_code: "MAD",
      sub_type: "AIRPORT",
      name: "Adolfo Suarez Barajas",
      city_name: "Madrid",
      country_name: "Spain",
      search_code: "MAD+",
    },
  ];

  it("suggests airports and cities and searches with the picked code", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.startsWith("/api/deals")) {
        return Promise.resolve(new Response(JSON.stringify({ deals: [] })));
      }
      if (url.startsWith("/api/locations")) {
        return Promise.resolve(new Response(JSON.stringify({ results: madrid })));
      }
      return Promise.resolve(new Response(JSON.stringify({ results: [] })));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    type("Origin", "tlv");
    type("Destination", "madr");

    const list = await screen.findByRole("listbox", { name: "Destination suggestions" });
    const option = within(list).getByRole("option", {
      name: /Adolfo Suarez Barajas, Madrid \(MAD\)/,
    });
    expect(within(list).getByRole("option", { name: /^City Madrid \(MAD\)/ })).toBeTruthy();
    fireEvent.mouseDown(option);
    expect((screen.getByLabelText("Destination") as HTMLInputElement).value).toBe(
      "Adolfo Suarez Barajas, Madrid (MAD)",
    );

    type("Date", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("destination=MAD%2B"))).toBe(
        true,
      ),
    );
    // The keyword went to our backend; the browser never talks to Amadeus.
    expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith("/api/"))).toBe(true);
  });

  it("does not ask for suggestions under two characters", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(
        new Response(JSON.stringify(url.includes("/deals") ? { deals: [] } : { results: [] })),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    type("Origin", "t");
    await new Promise((r) => setTimeout(r, 350));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/locations"))).toBe(false);
  });

  it("refuses to submit free text that is neither picked nor a code", () => {
    const onSearch = vi.fn();
    render(<SearchForm onSearch={onSearch} disabled={false} />);
    type("Origin", "Tel Aviv");
    type("Destination", "MAD");
    type("Date", "2099-01-01");
    fireEvent.submit(screen.getByRole("button", { name: "Search" }).closest("form")!);
    expect(onSearch).not.toHaveBeenCalled();
    expect(screen.getByText(/Pick an airport or city from the list/)).toBeTruthy();
  });

  it("resolves typed codes and picked codes", () => {
    expect(resolveCode({ text: "tlv", code: null })).toBe("TLV");
    expect(resolveCode({ text: "Madrid (MAD)", code: "MAD+" })).toBe("MAD+");
    expect(resolveCode({ text: "Madrid", code: null })).toBe("");
  });
});

describe("local times", () => {
  it("shows airport-local times without converting them", () => {
    expect(localTime("2099-01-01T23:15:00+01:00")).toBe("23:15");
    expect(localTime("2099-01-01T21:00:00Z")).toBe("21:00");
    expect(dayDifference("2027-03-27T18:00:00Z", "2027-03-29T09:40:00+08:00")).toBe(2);
  });
});

describe("price formatting", () => {
  it("formats with the currency the API sent, never a hardcoded one", () => {
    expect(formatPrice(1234, "ILS")).toBe("₪1,234");
    expect(formatPrice(1234.4, "USD")).toBe("$1,234");
    expect(formatPrice(99, "EUR")).toBe("€99");
    // a code Intl rejects must not crash the page
    expect(formatPrice(50, "NOPE!")).toBe("50 NOPE!");
  });
});

describe("layover time", () => {
  it("uses the UTC offsets, not the local clocks", () => {
    // lands 18:00 in Rome (+01:00), leaves 21:45 in Rome: 3h 45m
    expect(minutesBetween("2099-01-01T18:00:00+01:00", "2099-01-01T21:45:00+01:00")).toBe(225);
    // different offsets: 23:00-05:00 is 04:00Z, 06:30+02:00 is 04:30Z -> 30 minutes
    expect(minutesBetween("2099-01-01T23:00:00-05:00", "2099-01-02T06:30:00+02:00")).toBe(30);
  });
});
