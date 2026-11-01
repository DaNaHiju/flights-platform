import { useEffect, useState } from "react";
import { ApiError, listDeals, searchFlights, searchRoundTrip } from "./api";
import { DealItem } from "./DealItem";
import { OneWayItem, RoundTripItem } from "./OfferItem";
import { SearchForm } from "./SearchForm";
import type { Deal, FlightOffer, RoundTripOffer, SearchQuery } from "./types";

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

// One leg of a multi-city trip. Each leg is searched on its own, so one can fail
// (e.g. the provider answers 502) while the other still shows its results.
interface Leg {
  origin: string;
  destination: string;
  date: string;
  offers?: FlightOffer[];
  error?: string;
}

async function searchLeg(
  origin: string,
  destination: string,
  date: string,
): Promise<Leg> {
  try {
    return { origin, destination, date, offers: await searchFlights(origin, destination, date) };
  } catch (err) {
    return { origin, destination, date, error: errorText(err) };
  }
}

type Results =
  | { kind: "one-way"; query: SearchQuery; offers: FlightOffer[] }
  | { kind: "round-trip"; query: SearchQuery; offers: RoundTripOffer[] }
  | { kind: "multi-city"; legs: Leg[] };

function cheapest(offers: FlightOffer[] | undefined): FlightOffer | undefined {
  return offers?.reduce<FlightOffer | undefined>(
    (best, o) => (!best || o.price < best.price ? o : best),
    undefined,
  );
}

function MultiCityTotal({ legs }: { legs: Leg[] }) {
  const picks = legs.map((leg) => cheapest(leg.offers));
  if (picks.some((p) => !p) || new Set(picks.map((p) => p!.currency)).size !== 1) {
    return null;
  }
  const total = picks.reduce((sum, p) => sum + p!.price, 0);
  return (
    <p>
      <strong>
        Total: {total} {picks[0]!.currency}
      </strong>{" "}
      (cheapest option of each leg; price of two separate tickets)
    </p>
  );
}

export default function App() {
  const [results, setResults] = useState<Results | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [dealsError, setDealsError] = useState<string | null>(null);

  useEffect(() => {
    listDeals()
      .then(setDeals)
      .catch((err) => setDealsError(errorText(err)));
  }, []);

  async function handleSearch(query: SearchQuery) {
    setSearching(true);
    setSearchError(null);
    setResults(null);
    try {
      if (query.mode === "multi-city") {
        const legs = await Promise.all([
          searchLeg(query.origin, query.destination, query.date),
          searchLeg(query.origin2, query.destination2, query.date2),
        ]);
        setResults({ kind: "multi-city", legs });
      } else if (query.mode === "round-trip") {
        const offers = await searchRoundTrip(
          query.origin,
          query.destination,
          query.date,
          query.returnDate,
        );
        setResults({ kind: "round-trip", query, offers });
      } else {
        const offers = await searchFlights(query.origin, query.destination, query.date);
        setResults({ kind: "one-way", query, offers });
      }
    } catch (err) {
      setSearchError(errorText(err));
    } finally {
      setSearching(false);
    }
  }

  return (
    <main>
      <h1>Flights</h1>

      <section>
        <h2>Search flights</h2>
        <SearchForm onSearch={handleSearch} disabled={searching} />
        {searching && <p>Searching…</p>}
        {searchError && <p role="alert">{searchError}</p>}

        {results?.kind === "one-way" &&
          (results.offers.length === 0 ? (
            <p>No flights found for this search.</p>
          ) : (
            <ul className="offers">
              {results.offers.map((offer) => (
                <OneWayItem
                  key={offer.offer_id}
                  offer={offer}
                  origin={results.query.origin}
                  destination={results.query.destination}
                  date={results.query.date}
                />
              ))}
            </ul>
          ))}

        {results?.kind === "round-trip" &&
          (results.offers.length === 0 ? (
            <p>No flights found for this search.</p>
          ) : (
            <ul className="offers">
              {results.offers.map((offer) => (
                <RoundTripItem
                  key={`${offer.outbound.offer_id}-${offer.return.offer_id}`}
                  offer={offer}
                  origin={results.query.origin}
                  destination={results.query.destination}
                  date={results.query.date}
                  returnDate={results.query.returnDate}
                />
              ))}
            </ul>
          ))}

        {results?.kind === "multi-city" && (
          <>
            <MultiCityTotal legs={results.legs} />
            {results.legs.map((leg, i) => (
              <div key={i}>
                <h3>
                  Leg {i + 1}: {leg.origin} → {leg.destination} · {leg.date}
                </h3>
                {leg.error && <p role="alert">{leg.error}</p>}
                {leg.offers?.length === 0 && <p>No flights found for this leg.</p>}
                {leg.offers && leg.offers.length > 0 && (
                  <ul className="offers">
                    {leg.offers.map((offer) => (
                      <OneWayItem
                        key={offer.offer_id}
                        offer={offer}
                        origin={leg.origin}
                        destination={leg.destination}
                        date={leg.date}
                      />
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </>
        )}
      </section>

      <section>
        <h2>Deals</h2>
        {dealsError && <p>{dealsError}</p>}
        {!deals && !dealsError && <p>Loading…</p>}
        {deals && (
          <ul className="offers">
            {deals.map((deal) => (
              <DealItem key={`${deal.destination}-${deal.departure_date}`} deal={deal} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
