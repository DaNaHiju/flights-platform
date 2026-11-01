import { useState, type FormEvent } from "react";
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
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [date, setDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [origin2, setOrigin2] = useState("");
  const [destination2, setDestination2] = useState("");
  const [date2, setDate2] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSearch({
      mode,
      origin: origin.toUpperCase(),
      destination: destination.toUpperCase(),
      date,
      returnDate,
      origin2: origin2.toUpperCase(),
      destination2: destination2.toUpperCase(),
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
      <label>
        Origin
        <input
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="TLV"
          maxLength={3}
          pattern="[A-Za-z]{3}"
          required
        />
      </label>
      <label>
        Destination
        <input
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="MAD"
          maxLength={3}
          pattern="[A-Za-z]{3}"
          required
        />
      </label>
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
          <label>
            Origin 2
            <input
              value={origin2}
              onChange={(e) => setOrigin2(e.target.value)}
              placeholder="ATH"
              maxLength={3}
              pattern="[A-Za-z]{3}"
              required
            />
          </label>
          <label>
            Destination 2
            <input
              value={destination2}
              onChange={(e) => setDestination2(e.target.value)}
              placeholder="TLV"
              maxLength={3}
              pattern="[A-Za-z]{3}"
              required
            />
          </label>
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
    </form>
  );
}
