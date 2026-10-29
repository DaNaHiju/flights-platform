import { useEffect, useState } from "react";
import { ApiError, listDeals, searchFlights } from "./api";
import { SearchForm } from "./SearchForm";
import type { Deal, FlightOffer } from "./types";

function formatDuration(minutes: number): string {
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Algo salió mal.";
}

export default function App() {
  const [offers, setOffers] = useState<FlightOffer[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [dealsError, setDealsError] = useState<string | null>(null);

  useEffect(() => {
    listDeals()
      .then(setDeals)
      .catch((err) => setDealsError(errorText(err)));
  }, []);

  async function handleSearch(origin: string, destination: string, date: string) {
    setSearching(true);
    setSearchError(null);
    setOffers(null);
    try {
      setOffers(await searchFlights(origin, destination, date));
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
        <h2>Buscar vuelos</h2>
        <SearchForm onSearch={handleSearch} disabled={searching} />
        {searching && <p>Buscando…</p>}
        {searchError && <p role="alert">{searchError}</p>}
        {offers && offers.length === 0 && <p>No hay vuelos para esa búsqueda.</p>}
        {offers && offers.length > 0 && (
          <ul className="offers">
            {offers.map((offer) => (
              <li key={offer.offer_id}>
                <strong>
                  {offer.price} {offer.currency}
                </strong>{" "}
                · {offer.primary_airline} ·{" "}
                {offer.stops === 0 ? "directo" : `${offer.stops} escala(s)`} ·{" "}
                {formatDuration(offer.duration_minutes)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>Ofertas</h2>
        {dealsError && <p>{dealsError}</p>}
        {!deals && !dealsError && <p>Cargando…</p>}
        {deals && (
          <ul className="offers">
            {deals.map((deal) => (
              <li key={`${deal.destination}-${deal.departure_date}`}>
                <strong>{deal.destination}</strong> · {deal.departure_date} ·{" "}
                {deal.price} {deal.currency} · {deal.airline}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
