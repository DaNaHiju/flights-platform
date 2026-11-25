import { useState, type FormEvent } from "react";
import { AirportInput, EMPTY_AIRPORT, resolveCode, type AirportValue } from "./AirportInput";
import type { SearchQuery, TripMode } from "./types";

interface Props {
  onSearch: (query: SearchQuery) => void;
  disabled: boolean;
}

const MODES: { value: TripMode; label: string }[] = [
  { value: "one-way", label: "One way" },
  { value: "round-trip", label: "Round trip" },
  { value: "multi-city", label: "Multi-city" },
];

export function SearchForm({ onSearch, disabled }: Props) {
  const [mode, setMode] = useState<TripMode>("one-way");
  const [origin, setOrigin] = useState<AirportValue>(EMPTY_AIRPORT);
  const [destination, setDestination] = useState<AirportValue>(EMPTY_AIRPORT);
  const [date, setDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [origin2, setOrigin2] = useState<AirportValue>(EMPTY_AIRPORT);
  const [destination2, setDestination2] = useState<AirportValue>(EMPTY_AIRPORT);
  const [date2, setDate2] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

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

  return (
    <form onSubmit={handleSubmit} className="search">
      <label>
        Trip type
        <select value={mode} onChange={(e) => setMode(e.target.value as TripMode)}>
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <AirportInput label="Origin" value={origin} onChange={setOrigin} placeholder="City or airport" />
      <AirportInput label="Destination" value={destination} onChange={setDestination} placeholder="City or airport" />
      <label>
        Date
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          required
        />
      </label>
      {mode === "round-trip" && (
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
      )}
      {mode === "multi-city" && (
        <>
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
            <input
              type="date"
              value={date2}
              onChange={(e) => setDate2(e.target.value)}
              required
            />
          </label>
        </>
      )}
      <button type="submit" disabled={disabled}>
        Search
      </button>
      {formError && <p className="form-error">{formError}</p>}
    </form>
  );
}
