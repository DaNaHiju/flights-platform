/// <reference types="vite/client" />
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { DealItem } from "./DealItem";
import { DestinationBanner } from "./DestinationPhoto";
import type { Deal, FlightOffer, Leg } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PHOTO = {
  available: true,
  url: "/destination-image/file/hanoi_vietnam",
  credit_user: "Jane",
  credit_url: "https://pixabay.com/photos/hanoi-1234/",
};
const NO_PHOTO = { available: false, url: null, credit_user: null, credit_url: null };

// Answers /api/destination-image with `image`, and everything else with `others`.
function stubFetch(image: unknown, others: Record<string, unknown> = {}) {
  const fetchMock = vi.fn((url: string) => {
    if (url.startsWith("/api/destination-image")) {
      return image instanceof Error
        ? Promise.reject(image)
        : Promise.resolve(new Response(JSON.stringify(image)));
    }
    const key = Object.keys(others).find((fragment) => url.startsWith(`/api/${fragment}`));
    return Promise.resolve(new Response(JSON.stringify(key ? others[key] : { results: [] })));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("DestinationBanner", () => {
  const place = { city: "Hanoi", country: "Vietnam" };

  it("shows the photo, the place name and the credit linking to Pixabay", async () => {
    const fetchMock = stubFetch(PHOTO);
    render(<DestinationBanner place={place} />);

    expect(screen.getByText("Hanoi, Vietnam")).toBeTruthy();
    // while loading: the gradient, no image yet
    expect(screen.queryByRole("img")).toBeNull();

    const img = await screen.findByRole("img", { name: "View of Hanoi, Vietnam" });
    // served by our own backend, through the same /api prefix
    expect(img.getAttribute("src")).toBe("/api/destination-image/file/hanoi_vietnam");
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      "/api/destination-image?city=Hanoi&country=Vietnam",
    );

    const credit = screen.getByRole("link", { name: "Photo: Jane on Pixabay" });
    expect(credit.getAttribute("href")).toBe("https://pixabay.com/photos/hanoi-1234/");
    expect(credit.getAttribute("rel")).toContain("noopener");
  });

  it("keeps the gradient and shows no credit when there is no photo", async () => {
    const fetchMock = stubFetch(NO_PHOTO);
    render(<DestinationBanner place={place} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText("Hanoi, Vietnam")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText(/Pixabay/)).toBeNull();
  });

  it("keeps the gradient when the request fails", async () => {
    const fetchMock = stubFetch(new Error("offline"));
    render(<DestinationBanner place={place} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText("Hanoi, Vietnam")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("drops the photo AND its credit when the image itself fails to load", async () => {
    stubFetch(PHOTO);
    render(<DestinationBanner place={place} />);
    fireEvent.error(await screen.findByRole("img"));
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText(/Pixabay/)).toBeNull();
  });
});

describe("deal photos", () => {
  const deal: Deal = {
    destination: "FCO",
    departure_date: "2099-01-12",
    price: 120,
    currency: "USD",
    airline: "ITA Airways",
    origin: "TLV",
    destination_city: "Rome",
    destination_country_code: "IT",
  };

  it("asks for the destination city and its country name, with lazy loading and a credit", async () => {
    const fetchMock = stubFetch({
      ...PHOTO,
      url: "/destination-image/file/rome_italy",
      credit_user: "Marco",
    });
    render(
      <ul>
        <DealItem deal={deal} />
      </ul>,
    );
    const img = await screen.findByRole("img", { name: "View of Rome, Italy" });
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      "/api/destination-image?city=Rome&country=Italy",
    );
    expect(img.getAttribute("src")).toBe("/api/destination-image/file/rome_italy");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(screen.getByRole("link", { name: "Photo: Marco on Pixabay" })).toBeTruthy();
  });

  it("makes no request for a deal cached without a city", async () => {
    const fetchMock = stubFetch(PHOTO);
    render(
      <ul>
        <DealItem deal={{ ...deal, destination_city: null }} />
      </ul>,
    );
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("keeps the gradient when the photo does not exist", async () => {
    const fetchMock = stubFetch(NO_PHOTO);
    render(
      <ul>
        <DealItem deal={deal} />
      </ul>,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("Rome, Italy")).toBeTruthy();
  });
});

describe("results banner", () => {
  function leg(over: Partial<Leg> = {}): Leg {
    return {
      airline: "ITA Airways",
      flight_number: "AZ1",
      departure_airport: "Ben Gurion",
      arrival_airport: "Noi Bai",
      departure_datetime: "2099-01-01T08:00:00+02:00",
      arrival_datetime: "2099-01-01T20:00:00+07:00",
      duration_minutes: 600,
      arrival_city: "Hanoi",
      arrival_country_code: "VN",
      ...over,
    };
  }
  const offer: FlightOffer = {
    offer_id: "a",
    price: 500,
    currency: "USD",
    duration_minutes: 600,
    stops: 0,
    primary_airline: "ITA Airways",
    legs: [leg()],
  };
  const hanoi = [
    {
      id: "AHAN",
      iata_code: "HAN",
      sub_type: "AIRPORT",
      name: "Noi Bai",
      city_name: "Hanoi",
      country_name: "Vietnam",
      search_code: "HAN+",
    },
  ];

  function search(destination: string) {
    fireEvent.change(screen.getByLabelText("Origin"), { target: { value: "tlv" } });
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: destination } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2099-01-01" } });
  }

  it("shows the picked place, with its photo and credit, above the results", async () => {
    const fetchMock = stubFetch(PHOTO, {
      deals: { deals: [] },
      locations: { results: hanoi },
      flights: { results: [offer] },
    });
    render(<App />);
    search("noi");
    const option = await screen.findByRole("option", { name: /Noi Bai, Hanoi \(HAN\)/ });
    fireEvent.mouseDown(option);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("img", { name: "View of Hanoi, Vietnam" })).toBeTruthy();
    expect(screen.getByText("Hanoi, Vietnam")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Photo: Jane on Pixabay" })).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(
        ([url]) => String(url) === "/api/destination-image?city=Hanoi&country=Vietnam",
      ),
    ).toBe(true);
  });

  it("takes the city of the first result when a code was typed by hand", async () => {
    const fetchMock = stubFetch(PHOTO, {
      deals: { deals: [] },
      flights: { results: [offer] },
    });
    render(<App />);
    search("han");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("img", { name: "View of Hanoi, Vietnam" })).toBeTruthy();
    expect(screen.getByText("Hanoi, Vietnam")).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(
        ([url]) => String(url) === "/api/destination-image?city=Hanoi&country=Vietnam",
      ),
    ).toBe(true);
  });

  it("shows no strip when a typed code has no city to name", async () => {
    stubFetch(PHOTO, {
      deals: { deals: [] },
      flights: { results: [{ ...offer, legs: [leg({ arrival_city: null })] }] },
    });
    render(<App />);
    search("han");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText(/Flights/);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("Hanoi, Vietnam")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("keeps the strip, over the gradient, when the photo is unavailable", async () => {
    stubFetch(NO_PHOTO, {
      deals: { deals: [] },
      flights: { results: [offer] },
    });
    render(<App />);
    search("han");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Hanoi, Vietnam")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
