import { useEffect, useRef, useState } from "react";
import { ApiError, listDeals, searchFlights, searchRoundTrip } from "./api";
import { DealItem } from "./DealItem";
import { PlaneIcon } from "./Icons";
import { MultiCityFlow, NO_FLIGHTS_MESSAGE, OneWayFlow, RoundTripFlow, type LegSearch } from "./Flows";
import { SearchForm, type Prefill } from "./SearchForm";
import type { Deal, FlightOffer, RoundTripOffer, SearchQuery } from "./types";

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

async function searchLeg(
  origin: string,
  destination: string,
  date: string,
  adults: number,
): Promise<LegSearch> {
  try {
    return {
      origin,
      destination,
      date,
      offers: await searchFlights(origin, destination, date, adults),
    };
  } catch (err) {
    return { origin, destination, date, error: errorText(err) };
  }
}

type Results =
  | { kind: "one-way"; query: SearchQuery; offers: FlightOffer[] }
  | { kind: "round-trip"; query: SearchQuery; offers: RoundTripOffer[] }
  | { kind: "multi-city"; legs: LegSearch[]; adults: number };

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
          searchLeg(query.origin, query.destination, query.date, query.adults),
          searchLeg(query.origin2, query.destination2, query.date2, query.adults),
        ]);
        setResults({ kind: "multi-city", legs, adults: query.adults });
      } else if (query.mode === "round-trip") {
        const offers = await searchRoundTrip(
          query.origin,
          query.destination,
          query.date,
          query.returnDate,
          query.adults,
        );
        setResults({ kind: "round-trip", query, offers });
      } else {
        const offers = await searchFlights(
          query.origin,
          query.destination,
          query.date,
          query.adults,
        );
        setResults({ kind: "one-way", query, offers });
      }
    } catch (err) {
      setSearchError(errorText(err));
    } finally {
      setSearching(false);
    }
  }

  // A deal's "See flights": fill the form, search live and scroll to the results.
  // A round-trip deal opens the form in Round trip with both of its dates. The
  // deal's cached price is not reused: the search shows the current fares.
  function handleSeeFlights(deal: Deal) {
    if (!deal.origin) return;
    setPrefill({
      id: Date.now(),
      origin: deal.origin,
      destination: deal.destination,
      date: deal.departure_date,
      returnDate: deal.return_date,
    });
    void handleSearch({
      mode: deal.return_date ? "round-trip" : "one-way",
      adults: 1,
      origin: deal.origin,
      destination: deal.destination,
      date: deal.departure_date,
      returnDate: deal.return_date ?? "",
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
                  <p className="status">{NO_FLIGHTS_MESSAGE}</p>
                ) : (
                  <OneWayFlow offers={results.offers} adults={results.query.adults} />
                ))}

              {results?.kind === "round-trip" &&
                (results.offers.length === 0 ? (
                  <p className="status">{NO_FLIGHTS_MESSAGE}</p>
                ) : (
                  <RoundTripFlow offers={results.offers} adults={results.query.adults} />
                ))}

              {results?.kind === "multi-city" && <MultiCityFlow legs={results.legs} adults={results.adults} />}
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
