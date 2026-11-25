import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FlightRow } from "./FlightRow";
import type { FlightOffer, Leg } from "./types";

afterEach(cleanup);

function leg(over: Partial<Leg>): Leg {
  return {
    airline: "ITA Airways",
    airline_code: "AZ",
    flight_number: "AZ809",
    departure_airport: "Ben Gurion Airport",
    arrival_airport: "Fiumicino Airport",
    departure_datetime: "2099-01-01T08:00:00+02:00",
    arrival_datetime: "2099-01-01T11:00:00+01:00",
    duration_minutes: 240,
    departure_airport_code: "TLV",
    arrival_airport_code: "FCO",
    departure_city: "Tel Aviv",
    arrival_city: "Rome",
    ...over,
  };
}

function offer(legs: Leg[], over: Partial<FlightOffer> = {}): FlightOffer {
  return {
    offer_id: "x",
    price: 800,
    currency: "ILS",
    duration_minutes: 1200,
    stops: legs.length - 1,
    primary_airline: "ITA Airways",
    primary_airline_code: "AZ",
    legs,
    ...over,
  };
}

// TLV -> FCO (ITA), 3h 45m in Rome, FCO -> HND (ANA) landing the next day.
const connecting = offer(
  [
    leg({}),
    leg({
      airline: "ANA",
      airline_code: "NH",
      flight_number: "NH218",
      operating_airline: "Japan Airlines",
      departure_airport: "Fiumicino Airport",
      arrival_airport: "Haneda Airport",
      departure_datetime: "2099-01-01T14:45:00+01:00",
      arrival_datetime: "2099-01-02T10:05:00+09:00",
      duration_minutes: 740,
      departure_airport_code: "FCO",
      arrival_airport_code: "HND",
      departure_city: "Rome",
      arrival_city: "Tokyo",
    }),
  ],
  { duration_minutes: 1100 },
);

function row(o: FlightOffer, deepLink: string | null = "https://book.example/x") {
  render(
    <ul>
      <FlightRow directions={[{ offer: o }]} price={o.price} currency="ILS" deepLink={deepLink} />
    </ul>,
  );
}

describe("FlightRow closed", () => {
  it("shows airlines, local times with +N, duration, codes and stops with airports", () => {
    row(connecting);
    expect(screen.getByText("ITA Airways, ANA")).toBeTruthy();
    expect(screen.getByText(/08:00 → 10:05/)).toBeTruthy();
    expect(screen.getByText(/\+1/)).toBeTruthy();
    expect(screen.getByText("18h 20m")).toBeTruthy();
    expect(screen.getByText("TLV")).toBeTruthy();
    expect(screen.getByText("HND")).toBeTruthy();
    expect(screen.getByText("1 stop · FCO")).toBeTruthy();
    expect(screen.getByText("₪800")).toBeTruthy();
    expect(screen.getByText("one way")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("FlightRow open", () => {
  it("shows the layover from the timestamps with their offsets", () => {
    row(connecting);
    fireEvent.click(screen.getByRole("button"));
    // lands 11:00+01:00, leaves 14:45+01:00
    expect(screen.getByText(/3h 45m\s+layover · Rome \(FCO\)/)).toBeTruthy();
    expect(screen.getByText(/operated by Japan Airlines/)).toBeTruthy();
    expect(screen.getByText(/ANA NH218/)).toBeTruthy();
    expect(screen.queryByText("Overnight")).toBeNull();
    expect(screen.queryByText("Airport change")).toBeNull();
    expect(screen.getByRole("button").getAttribute("aria-expanded")).toBe("true");
  });

  it("flags an overnight layover and an airport change", () => {
    const night = offer([
      leg({ arrival_datetime: "2099-01-01T23:10:00+01:00" }),
      leg({
        flight_number: "AZ1",
        departure_airport_code: "CIA",
        departure_datetime: "2099-01-02T07:00:00+01:00",
        arrival_airport_code: "LIN",
        arrival_datetime: "2099-01-02T09:00:00+01:00",
      }),
    ]);
    row(night);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Overnight")).toBeTruthy();
    expect(screen.getByText("Airport change")).toBeTruthy();
    expect(screen.getByText(/7h 50m\s+layover/)).toBeTruthy();
  });

  it("shows Book only with a deep link, and Go to for mapped airlines", () => {
    row(connecting, null);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByRole("link", { name: "Book" })).toBeNull();
    expect(screen.getByRole("link", { name: "Go to ITA Airways" })).toBeTruthy();
    // ANA is not in the map
    expect(screen.queryByRole("link", { name: "Go to ANA" })).toBeNull();
  });

  it("books through the deep link", () => {
    row(connecting);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("link", { name: "Book" }).getAttribute("href")).toBe(
      "https://book.example/x",
    );
  });

  it("collapses on a second click", () => {
    row(connecting);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText(/layover/)).toBeNull();
  });
});

describe("FlightRow round trip", () => {
  it("has two lines, one total price and both timelines when open", () => {
    const back = offer([
      leg({
        flight_number: "AZ810",
        departure_airport_code: "FCO",
        arrival_airport_code: "TLV",
        departure_city: "Rome",
        arrival_city: "Tel Aviv",
      }),
    ]);
    render(
      <ul>
        <FlightRow
          directions={[
            { label: "Outbound", offer: offer([leg({})]) },
            { label: "Return", offer: back },
          ]}
          price={1500}
          currency="ILS"
        />
      </ul>,
    );
    expect(screen.getAllByText("Nonstop")).toHaveLength(2);
    expect(screen.getAllByText("₪1,500")).toHaveLength(1);
    expect(screen.getByText("round trip")).toBeTruthy();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getAllByText("Outbound").length).toBeGreaterThan(0);
    expect(screen.getByText(/AZ810/)).toBeTruthy();
  });
});
