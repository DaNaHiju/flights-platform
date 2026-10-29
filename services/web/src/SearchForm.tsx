import { useState, type FormEvent } from "react";

interface Props {
  onSearch: (origin: string, destination: string, date: string) => void;
  disabled: boolean;
}

export function SearchForm({ onSearch, disabled }: Props) {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [date, setDate] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSearch(origin.toUpperCase(), destination.toUpperCase(), date);
  }

  return (
    <form onSubmit={handleSubmit} className="search">
      <label>
        Origen
        <input
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="EZE"
          maxLength={3}
          pattern="[A-Za-z]{3}"
          required
        />
      </label>
      <label>
        Destino
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
        Fecha
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          required
        />
      </label>
      <button type="submit" disabled={disabled}>
        Buscar
      </button>
    </form>
  );
}
