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
import { airlineDisplayName, airlineUrl } from "./airlines";
import { SearchForm } from "./SearchForm";
import { DealItem } from "./DealItem";
import { countryName, formatDuration, placeLabel } from "./format";
import type { Deal, FlightOffer, Leg } from "./types";

function offer(id: string, price: number, airline: string): FlightOffer {
  return {
    offer_id: id,
    price,
    currency: "USD",
    duration_minutes: 200,
    stops: 0,
    primary_airline: airline,
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

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
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

    const selector = screen.getByLabelText("Trip type");
    const options = within(selector).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["One way", "Round trip", "Multi-city"]);

    expect(screen.queryByLabelText("Return")).toBeNull();
    fireEvent.change(selector, { target: { value: "round-trip" } });
    expect(screen.getByLabelText("Return")).toBeTruthy();

    fireEvent.change(selector, { target: { value: "multi-city" } });
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

describe("multi-city", () => {
  it("shows the error of a failed leg and still shows the other leg", async () => {
    mockFetch([
      ["origin=TLV", 200, { results: [offer("a", 150, "El Al")] }],
      ["origin=ATH", 502, { error: "provider_unavailable" }],
    ]);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Trip type"), {
      target: { value: "multi-city" },
    });
    type("Origin", "tlv");
    type("Destination", "ath");
    type("Date", "2099-01-01");
    type("Origin 2", "ath");
    type("Destination 2", "tlv");
    type("Date 2", "2099-01-08");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    // exactly one error, and it is the provider-down message of leg 2
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(PROVIDER_DOWN_MESSAGE),
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    // leg 1 still lists its offer
    expect(screen.getByText(/150 USD/)).toBeTruthy();
    expect(screen.getByText(/Leg 1: TLV → ATH/)).toBeTruthy();
    expect(screen.getByText(/Leg 2: ATH → TLV/)).toBeTruthy();
    // no total while a leg is missing
    expect(screen.queryByText(/two separate tickets/)).toBeNull();
  });

  it("adds both legs into a total labelled as two separate tickets", async () => {
    mockFetch([
      ["origin=TLV", 200, { results: [offer("a", 150, "El Al"), offer("b", 90, "Ryanair")] }],
      ["origin=ATH", 200, { results: [offer("c", 70, "Aegean Airlines")] }],
    ]);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Trip type"), {
      target: { value: "multi-city" },
    });
    type("Origin", "tlv");
    type("Destination", "ath");
    type("Date", "2099-01-01");
    type("Origin 2", "ath");
    type("Destination 2", "tlv");
    type("Date 2", "2099-01-08");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    // cheapest of each leg: 90 + 70
    await waitFor(() => expect(screen.getByText(/Total: 160 USD/)).toBeTruthy());
    expect(screen.getByText(/price of two separate tickets/)).toBeTruthy();
  });
});

describe("round trip", () => {
  it("sends return_date and lists the pair with one price", async () => {
    mockFetch([
      [
        "return_date=2099-01-08",
        200,
        {
          results: [
            {
              price: 166,
              currency: "USD",
              outbound: offer("o", 144, "El Al"),
              return: offer("r", 166, "El Al"),
            },
          ],
        },
      ],
    ]);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Trip type"), {
      target: { value: "round-trip" },
    });
    type("Origin", "tlv");
    type("Destination", "ath");
    type("Date", "2099-01-01");
    type("Return", "2099-01-08");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(screen.getByText(/166 USD/)).toBeTruthy());
    expect(screen.queryByText(/144 USD/)).toBeNull();
  });
});

describe("booking links", () => {
  async function searchWith(airline: string) {
    mockFetch([["origin=TLV", 200, { results: [offer("a", 100, airline)] }]]);
    render(<App />);
    type("Origin", "tlv");
    type("Destination", "ath");
    type("Date", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText(/100 USD/)).toBeTruthy());
  }

  it("always has a Google Flights link, and an airline link when the airline is mapped", async () => {
    await searchWith("El Al");

    const book = screen.getByRole("link", { name: "Book" });
    expect(book.getAttribute("href")).toContain("https://www.google.com/travel/flights?q=");
    expect(decodeURIComponent(book.getAttribute("href")!)).toContain(
      "Flights to ATH from TLV on 2099-01-01 oneway",
    );
    expect(book.getAttribute("target")).toBe("_blank");
    expect(book.getAttribute("rel")).toBe("noopener noreferrer");

    const airline = screen.getByRole("link", { name: "Go to El Al" });
    expect(airline.getAttribute("href")).toBe(airlineUrl("El Al"));
    expect(airline.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("shows corrected airline names in the airline button", async () => {
    await searchWith("Lufthansa Cargo");
    expect(screen.getByRole("link", { name: "Go to Lufthansa" })).toBeTruthy();
    expect(airlineUrl("Lufthansa Cargo")).toBe("https://www.lufthansa.com");
    expect(airlineDisplayName("Alitalia")).toBe("ITA Airways");
    expect(airlineDisplayName("Nowhere Air")).toBe("Nowhere Air");
  });

  it("has no airline link when the airline is not in the map", async () => {
    await searchWith("Nowhere Air");

    expect(screen.getByRole("link", { name: "Book" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /^Go to/ })).toBeNull();
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

describe("offer details", () => {
  it("shows the route with city, country and airport, and the total duration", async () => {
    mockFetch([
      ["origin=TLV", 200, { results: [{ ...offer("a", 100, "El Al"), duration_minutes: 380, legs: [leg()] }] }],
    ]);
    render(<App />);
    type("Origin", "tlv");
    type("Destination", "fco");
    type("Date", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(screen.getByText(/Tel Aviv, Israel \(TLV\)/)).toBeTruthy(),
    );
    expect(screen.getByText(/Rome, Italy \(FCO\)/)).toBeTruthy();
    expect(screen.getByText(/Ben Gurion International Airport/)).toBeTruthy();
    expect(screen.getByText(/Direct · 6h 20m/)).toBeTruthy();
  });

  it("lists each segment and the layover for flights with a stop", async () => {
    const first = leg({
      arrival_airport: "Frankfurt Airport",
      arrival_airport_code: "FRA",
      arrival_city: "Frankfurt",
      arrival_country_code: "DE",
      duration_minutes: 255,
    });
    const second = leg({
      flight_number: "LH232",
      departure_airport: "Frankfurt Airport",
      departure_airport_code: "FRA",
      departure_city: "Frankfurt",
      departure_country_code: "DE",
      duration_minutes: 125,
    });
    mockFetch([
      ["origin=TLV", 200, { results: [{ ...offer("a", 100, "El Al"), stops: 1, duration_minutes: 500, legs: [first, second] }] }],
    ]);
    render(<App />);
    type("Origin", "tlv");
    type("Destination", "fco");
    type("Date", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(screen.getByText(/LY381/)).toBeTruthy());
    expect(screen.getByText(/LH232/)).toBeTruthy();
    expect(screen.getByText(/4h 15m/)).toBeTruthy();
    expect(screen.getByText(/2h 5m/)).toBeTruthy();
    expect(screen.getByText("Layover in Frankfurt, Germany (FRA)")).toBeTruthy();
    expect(screen.getByText(/1 stop · 8h 20m/)).toBeTruthy();
  });

  it("still renders an old offer whose legs lack the added fields", async () => {
    const old = leg();
    for (const key of Object.keys(old).filter((k) => /code|city/.test(k))) {
      delete (old as unknown as Record<string, unknown>)[key];
    }
    mockFetch([["origin=TLV", 200, { results: [{ ...offer("a", 100, "El Al"), legs: [old] }] }]]);
    render(<App />);
    type("Origin", "tlv");
    type("Destination", "fco");
    type("Date", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(screen.getByText(/100 USD/)).toBeTruthy());
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
    airline: "Alitalia",
  };

  it("shows origin → destination with city, country and airport", () => {
    render(
      <ul>
        <DealItem
          deal={{
            ...base,
            origin: "TLV",
            origin_city: "Tel Aviv",
            origin_country_code: "IL",
            origin_airport_name: "Ben Gurion International Airport",
            destination_city: "Rome",
            destination_country_code: "IT",
            destination_airport_name: "Fiumicino",
            total_duration_minutes: 260,
          }}
        />
      </ul>,
    );
    expect(screen.getByText(/Tel Aviv, Israel \(TLV\) → Rome, Italy \(FCO\)/)).toBeTruthy();
    expect(screen.getByText(/Ben Gurion International Airport → Fiumicino/)).toBeTruthy();
    expect(screen.getByText(/ITA Airways · 4h 20m/)).toBeTruthy();
  });

  it("tolerates a deal cached without the added fields", () => {
    render(
      <ul>
        <DealItem deal={base} />
      </ul>,
    );
    expect(screen.getByText("FCO")).toBeTruthy();
    expect(screen.getByText(/120 USD/)).toBeTruthy();
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
