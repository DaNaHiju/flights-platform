import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, listDeals, searchFlights, searchRoundTrip } from "./api";
import { DealItem } from "./DealItem";
import { displayCode, formatPrice } from "./format";
import { PlaneIcon } from "./Icons";
import { FlightRow } from "./FlightRow";
import { rankOneWay, rankRoundTrip } from "./results";
import { ResultsList } from "./ResultsList";
import { SearchForm, type Prefill } from "./SearchForm";
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

function OneWayList({ offers, label }: { offers: FlightOffer[]; label?: string }) {
  const ranked = useMemo(() => offers.map(rankOneWay), [offers]);
  return (
    <ResultsList
      results={ranked}
      label={label}
      renderRow={(offer) => (
        <FlightRow
          directions={[{ offer }]}
          price={offer.price}
          currency={offer.currency}
          deepLink={offer.deep_link}
        />
      )}
    />
  );
}

function RoundTripList({ offers }: { offers: RoundTripOffer[] }) {
  const ranked = useMemo(() => offers.map(rankRoundTrip), [offers]);
  return (
    <ResultsList
      results={ranked}
      renderRow={(offer) => (
        <FlightRow
          directions={[
            { label: "Outbound", offer: offer.outbound },
            { label: "Return", offer: offer.return },
          ]}
          price={offer.price}
          currency={offer.currency}
          deepLink={offer.deep_link}
        />
      )}
    />
  );
}

function MultiCityTotal({ legs }: { legs: Leg[] }) {
  const picks = legs.map((leg) => cheapest(leg.offers));
  if (picks.some((p) => !p) || new Set(picks.map((p) => p!.currency)).size !== 1) {
    return null;
  }
  const total = picks.reduce((sum, p) => sum + p!.price, 0);
  return (
    <p className="total">
      <strong>
        Total: {formatPrice(total, picks[0]!.currency)}
      </strong>{" "}
      (cheapest option of each leg; price of two separate tickets)
    </p>
  );
}

function Brand({ footer = false }: { footer?: boolean }) {
  return (
    <a className="brand" href="#top" aria-label="brisa, back to the top">
      {!footer && (
        <span className="brand-mark">
          <PlaneIcon />
        </span>
      )}
      brisa<span className="brand-dot">.</span>
    </a>
  );
}

export default function App() {
  const [results, setResults] = useState<Results | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [dealsError, setDealsError] = useState<string | null>(null);

  const [prefill, setPrefill] = useState<Prefill | null>(null);

  const resultsRef = useRef<HTMLElement>(null);

  useEffect(() => {
    listDeals()
      .then(setDeals)
      .catch((err) => setDealsError(errorText(err)));
  }, []);

  // Bring the results into view once a search finishes. Optional call: jsdom
  // (the tests) does not implement scrollIntoView.
  useEffect(() => {
    if (results || searchError) {
      resultsRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  }, [results, searchError]);

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

  // A deal's "See flights": fill the form, search live and scroll to the results.
  // The deal's cached price is not reused: the search shows the current fares.
  function handleSeeFlights(deal: Deal) {
    if (!deal.origin) return;
    setPrefill({
      id: Date.now(),
      origin: deal.origin,
      destination: deal.destination,
      date: deal.departure_date,
    });
    void handleSearch({
      mode: "one-way",
      origin: deal.origin,
      destination: deal.destination,
      date: deal.departure_date,
      returnDate: "",
      origin2: "",
      destination2: "",
      date2: "",
    });
  }

  const showResults = searching || searchError !== null || results !== null;

  return (
    <>
      <header className="site-header" id="top">
        <div className="wrap nav-inner">
          <Brand />
          <nav className="nav-links" aria-label="Main navigation">
            <a href="#top">Home</a>
            <a href="#deals">Deals</a>
            <a className="nav-pill" href="#search">
              Find flights
            </a>
          </nav>
        </div>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="wrap hero-content">
            <span className="eyebrow">The world is waiting</span>
            <h1 id="hero-title">
              Fly into your
              <br />
              next story.
            </h1>
            <p>Spontaneous escapes, dream trips, and unforgettable moments. Start exploring your next destination.</p>
          </div>
        </section>

        <section className="wrap search-section" id="search" aria-label="Flight search">
          <div className="search-card">
            <SearchForm onSearch={handleSearch} disabled={searching} prefill={prefill} />
          </div>
        </section>

        {showResults && (
          <section className="section-block results" id="results" ref={resultsRef}>
            <div className="wrap">
              <p className="section-kicker">Your search</p>
              <h2>Flights</h2>

              {searching && <p className="status">Searching…</p>}
              {searchError && <p role="alert">{searchError}</p>}

              {results?.kind === "one-way" &&
                (results.offers.length === 0 ? (
                  <p className="status">No flights found for this search.</p>
                ) : (
                  <OneWayList offers={results.offers} />
                ))}

              {results?.kind === "round-trip" &&
                (results.offers.length === 0 ? (
                  <p className="status">No flights found for this search.</p>
                ) : (
                  <RoundTripList offers={results.offers} />
                ))}

              {results?.kind === "multi-city" && (
                <>
                  <MultiCityTotal legs={results.legs} />
                  {results.legs.map((leg, i) => (
                    <div key={i}>
                      <h3 className="leg-title">
                        Leg {i + 1}: {displayCode(leg.origin)} → {displayCode(leg.destination)} ·{" "}
                        {leg.date}
                      </h3>
                      {leg.error && <p role="alert">{leg.error}</p>}
                      {leg.offers?.length === 0 && (
                        <p className="status">No flights found for this leg.</p>
                      )}
                      {leg.offers && leg.offers.length > 0 && (
                        <OneWayList offers={leg.offers} label={`Flights, leg ${i + 1}`} />
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          </section>
        )}

        <section className="section-block" id="deals">
          <div className="wrap">
            <p className="section-kicker">A little inspiration</p>
            <h2>Deals</h2>
            {dealsError && <p className="status">{dealsError}</p>}
            {!deals && !dealsError && <p className="status">Loading…</p>}
            {deals && (
              <ul className="offers deals-grid">
                {deals.map((deal) => (
                  <DealItem
                    key={`${deal.destination}-${deal.departure_date}`}
                    deal={deal}
                    onSeeFlights={handleSeeFlights}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="wrap footer-inner">
          <div>
            <Brand footer />
            <p>Fares and schedules come from the flight provider and can change before you book.</p>
          </div>
          <a className="footer-link" href="#top">
            Back to top ↑
          </a>
        </div>
      </footer>
    </>
  );
}
