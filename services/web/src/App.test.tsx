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
import { SearchForm } from "./SearchForm";
import type { FlightOffer } from "./types";

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

    expect(screen.getByLabelText("Origen")).toBeTruthy();
    expect(screen.getByLabelText("Destino")).toBeTruthy();
    expect(screen.getByLabelText("Fecha")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Buscar" })).toBeTruthy();
  });

  it("offers the three trip types and shows the extra fields of each", () => {
    render(<SearchForm onSearch={() => {}} disabled={false} />);

    const selector = screen.getByLabelText("Tipo de viaje");
    const options = within(selector).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Solo ida", "Ida y vuelta", "Multi-ciudad"]);

    expect(screen.queryByLabelText("Vuelta")).toBeNull();
    fireEvent.change(selector, { target: { value: "round-trip" } });
    expect(screen.getByLabelText("Vuelta")).toBeTruthy();

    fireEvent.change(selector, { target: { value: "multi-city" } });
    expect(screen.queryByLabelText("Vuelta")).toBeNull();
    expect(screen.getByLabelText("Origen 2")).toBeTruthy();
    expect(screen.getByLabelText("Destino 2")).toBeTruthy();
    expect(screen.getByLabelText("Fecha 2")).toBeTruthy();
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
    fireEvent.change(screen.getByLabelText("Origen"), { target: { value: "eze" } });
    fireEvent.change(screen.getByLabelText("Destino"), { target: { value: "mad" } });
    fireEvent.change(screen.getByLabelText("Fecha"), {
      target: { value: "2099-01-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

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
    fireEvent.change(screen.getByLabelText("Tipo de viaje"), {
      target: { value: "multi-city" },
    });
    type("Origen", "tlv");
    type("Destino", "ath");
    type("Fecha", "2099-01-01");
    type("Origen 2", "ath");
    type("Destino 2", "tlv");
    type("Fecha 2", "2099-01-08");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

    // exactly one error, and it is the provider-down message of leg 2
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(PROVIDER_DOWN_MESSAGE),
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    // leg 1 still lists its offer
    expect(screen.getByText(/150 USD/)).toBeTruthy();
    expect(screen.getByText(/Tramo 1: TLV → ATH/)).toBeTruthy();
    expect(screen.getByText(/Tramo 2: ATH → TLV/)).toBeTruthy();
    // no total while a leg is missing
    expect(screen.queryByText(/dos pasajes separados/)).toBeNull();
  });

  it("adds both legs into a total labelled as two separate tickets", async () => {
    mockFetch([
      ["origin=TLV", 200, { results: [offer("a", 150, "El Al"), offer("b", 90, "Ryanair")] }],
      ["origin=ATH", 200, { results: [offer("c", 70, "Aegean Airlines")] }],
    ]);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Tipo de viaje"), {
      target: { value: "multi-city" },
    });
    type("Origen", "tlv");
    type("Destino", "ath");
    type("Fecha", "2099-01-01");
    type("Origen 2", "ath");
    type("Destino 2", "tlv");
    type("Fecha 2", "2099-01-08");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

    // cheapest of each leg: 90 + 70
    await waitFor(() => expect(screen.getByText(/Total: 160 USD/)).toBeTruthy());
    expect(screen.getByText(/precio de dos pasajes separados/)).toBeTruthy();
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
    fireEvent.change(screen.getByLabelText("Tipo de viaje"), {
      target: { value: "round-trip" },
    });
    type("Origen", "tlv");
    type("Destino", "ath");
    type("Fecha", "2099-01-01");
    type("Vuelta", "2099-01-08");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

    await waitFor(() => expect(screen.getByText(/166 USD/)).toBeTruthy());
    expect(screen.queryByText(/144 USD/)).toBeNull();
  });
});

describe("booking links", () => {
  async function searchWith(airline: string) {
    mockFetch([["origin=TLV", 200, { results: [offer("a", 100, airline)] }]]);
    render(<App />);
    type("Origen", "tlv");
    type("Destino", "ath");
    type("Fecha", "2099-01-01");
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(screen.getByText(/100 USD/)).toBeTruthy());
  }

  it("always has a Google Flights link, and an airline link when the airline is mapped", async () => {
    await searchWith("El Al");

    const book = screen.getByRole("link", { name: "Reservar" });
    expect(book.getAttribute("href")).toContain("https://www.google.com/travel/flights?q=");
    expect(decodeURIComponent(book.getAttribute("href")!)).toContain(
      "Flights to ATH from TLV on 2099-01-01 oneway",
    );
    expect(book.getAttribute("target")).toBe("_blank");
    expect(book.getAttribute("rel")).toBe("noopener noreferrer");

    const airline = screen.getByRole("link", { name: "Ir a El Al" });
    expect(airline.getAttribute("href")).toBe(airlineUrl("El Al"));
    expect(airline.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("has no airline link when the airline is not in the map", async () => {
    await searchWith("Nowhere Air");

    expect(screen.getByRole("link", { name: "Reservar" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /^Ir a/ })).toBeNull();
  });
});

