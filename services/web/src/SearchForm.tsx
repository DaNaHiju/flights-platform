import { useEffect, useState, type FormEvent } from "react";
import { AirportInput, EMPTY_AIRPORT, resolveCode, type AirportValue } from "./AirportInput";
import { SearchIcon, SwapIcon } from "./Icons";
import type { SearchQuery, TripMode } from "./types";

// A search chosen outside the form (a deal's "See flights"). `id` changes on
// every request, so picking the same deal twice fills the form twice.
export interface Prefill {
  id: number;
  origin: string;
  destination: string;
  date: string;
  // Set for a round-trip deal: the form opens in Round trip with both dates.
  returnDate?: string | null;
}

interface Props {
  onSearch: (query: SearchQuery) => void;
  disabled: boolean;
  prefill?: Prefill | null;
}

const MODES: { value: TripMode; label: string }[] = [
  { value: "one-way", label: "One way" },
  { value: "round-trip", label: "Round trip" },
  { value: "multi-city", label: "Multi-city" },
];

export function SearchForm({ onSearch, disabled, prefill }: Props) {
  const [mode, setMode] = useState<TripMode>("one-way");
  const [origin, setOrigin] = useState<AirportValue>(EMPTY_AIRPORT);
  const [destination, setDestination] = useState<AirportValue>(EMPTY_AIRPORT);
  const [date, setDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [origin2, setOrigin2] = useState<AirportValue>(EMPTY_AIRPORT);
  const [destination2, setDestination2] = useState<AirportValue>(EMPTY_AIRPORT);
  const [date2, setDate2] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!prefill) return;
    setMode(prefill.returnDate ? "round-trip" : "one-way");
    setOrigin({ text: prefill.origin, code: prefill.origin });
    setDestination({ text: prefill.destination, code: prefill.destination });
    setDate(prefill.date);
    setReturnDate(prefill.returnDate ?? "");
    setFormError(null);
  }, [prefill]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const boxes = mode === "multi-city" ? [origin, destination, origin2, destination2] : [origin, destination];
    if (boxes.some((box) => resolveCode(box) === "")) {
      setFormError("Pick an airport or city from the list, or type a 3-letter code.");
      return;
    }
    setFormError(null);
    onSearch({
      mode,
      origin: resolveCode(origin),
      destination: resolveCode(destination),
      date,
      returnDate,
      origin2: resolveCode(origin2),
      destination2: resolveCode(destination2),
      date2,
    });
  }

  function swapCities() {
    setOrigin(destination);
    setDestination(origin);
  }

  const submit = (
    <button type="submit" className="primary-btn" disabled={disabled}>
      <SearchIcon />
      Search
    </button>
  );

  return (
    <form onSubmit={handleSubmit} className="search">
      <div className="search-top">
        <div className="trip-tabs" role="group" aria-label="Trip type">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              className="trip-tab"
              aria-pressed={mode === m.value}
              onClick={() => setMode(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <span className="search-note">Pick a city or airport, or type a 3-letter code</span>
      </div>

      {mode !== "multi-city" && (
        <div className="fields">
          <AirportInput label="Origin" value={origin} onChange={setOrigin} placeholder="City or airport" />
          <button
            type="button"
            className="swap"
            aria-label="Swap origin and destination"
            title="Swap"
            onClick={swapCities}
          >
            <SwapIcon />
          </button>
          <AirportInput
            label="Destination"
            value={destination}
            onChange={setDestination}
            placeholder="City or airport"
          />
          <label>
            Date
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          {mode === "round-trip" ? (
            <label>
              Return
              <input
                type="date"
                value={returnDate}
                min={date}
                onChange={(e) => setReturnDate(e.target.value)}
                required
              />
            </label>
          ) : (
            <span aria-hidden="true" />
          )}
          {submit}
        </div>
      )}

      {mode === "multi-city" && (
        <>
          <div className="multi-fields">
            <div className="multi-leg">
              <h3>Flight 1</h3>
              <div className="multi-leg-fields">
                <AirportInput label="Origin" value={origin} onChange={setOrigin} placeholder="City or airport" />
                <AirportInput
                  label="Destination"
                  value={destination}
                  onChange={setDestination}
                  placeholder="City or airport"
                />
                <label>
                  Date
                  <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
                </label>
              </div>
            </div>
            <div className="multi-leg">
              <h3>Flight 2</h3>
              <div className="multi-leg-fields">
                <AirportInput
                  label="Origin 2"
                  value={origin2}
                  onChange={setOrigin2}
                  placeholder="City or airport"
                />
                <AirportInput
                  label="Destination 2"
                  value={destination2}
                  onChange={setDestination2}
                  placeholder="City or airport"
                />
                <label>
                  Date 2
                  <input type="date" value={date2} onChange={(e) => setDate2(e.target.value)} required />
                </label>
              </div>
            </div>
          </div>
          <div className="search-actions">{submit}</div>
        </>
      )}

      {formError && <p className="form-error">{formError}</p>}
    </form>
  );
}
