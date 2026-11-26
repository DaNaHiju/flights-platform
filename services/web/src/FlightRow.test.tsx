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

function row(o: FlightOffer, deepLink: string | null = "https://book.example/x", review = false) {
  render(
    <ul>
      <FlightRow
        directions={[{ offer: o }]}
        price={o.price}
        currency="ILS"
        deepLink={deepLink}
        review={review}
      />
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
    expect(screen.queryAllByRole("link", { name: /^(Book|Go to)/ })).toHaveLength(0);
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

  it("never shows Book or Go to in a list, only in review", () => {
    row(connecting);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryAllByRole("link", { name: /^(Book|Go to)/ })).toHaveLength(0);
  });

  it("shows Book only with a deep link, and Go to for mapped airlines (review)", () => {
    row(connecting, null, true);
    expect(screen.queryByRole("link", { name: "Book" })).toBeNull();
    expect(screen.getByRole("link", { name: "Go to ITA Airways" })).toBeTruthy();
    // ANA is not in the map
    expect(screen.queryByRole("link", { name: "Go to ANA" })).toBeNull();
  });

  it("books through the deep link (review)", () => {
    row(connecting, "https://book.example/x", true);
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

describe("FlightRow choose", () => {
  it("has a Choose button next to the row that does not expand it", () => {
    let chosen = 0;
    render(
      <ul>
        <FlightRow
          directions={[{ offer: connecting }]}
          price={800}
          currency="ILS"
          pricePrefix="from"
          caption="2 return options"
          onChoose={() => chosen++}
        />
      </ul>,
    );
    expect(screen.getByText("from")).toBeTruthy();
    expect(screen.getByText("2 return options")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Choose" }));
    expect(chosen).toBe(1);
    expect(screen.queryByText(/layover/)).toBeNull();
  });
});

describe("checked bag badge", () => {
  const one = [leg({})];
  const piece = { type: "piece", quantity: 1, weight_amount: 23, weight_unit: "KG", applicable_legs: [1] };

  it("shows the allowance in the row", () => {
    render(<ul><FlightRow directions={[{ offer: offer(one, { checked_bags: [piece] }) }]} price={800} currency="ILS" /></ul>);
    expect(screen.getByText("1 checked bag · 23 kg")).toBeTruthy();
  });

  it("without the field it says the info is not available, and never 'No checked bag'", () => {
    render(<ul><FlightRow directions={[{ offer: offer(one) }]} price={800} currency="ILS" /></ul>);
    expect(screen.getByText("Checked bag info not available")).toBeTruthy();
    expect(screen.queryByText(/No checked bag/)).toBeNull();
  });

  it("an empty list from the API is 'No checked bag'", () => {
    render(<ul><FlightRow directions={[{ offer: offer(one, { checked_bags: [] }) }]} price={800} currency="ILS" /></ul>);
    expect(screen.getByText("No checked bag")).toBeTruthy();
  });

  it("a round trip shows each direction's own badge", () => {
    render(
      <ul>
        <FlightRow
          directions={[
            { label: "Outbound", offer: offer(one, { checked_bags: [piece] }) },
            { label: "Return", offer: offer(one) },
          ]}
          price={1200}
          currency="ILS"
        />
      </ul>,
    );
    expect(screen.getByText("1 checked bag · 23 kg")).toBeTruthy();
    expect(screen.getByText("Checked bag info not available")).toBeTruthy();
  });
});
