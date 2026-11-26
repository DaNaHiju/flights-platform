import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { searchLocations } from "./api";
import type { DestinationPlace, Location } from "./types";

// What the form keeps for one origin/destination box: the text shown, and the
// code picked from the list (null while the user is still typing).
export interface AirportValue {
  text: string;
  code: string | null;
  // The city and country of the picked suggestion; typing clears it.
  place?: DestinationPlace;
}

export const EMPTY_AIRPORT: AirportValue = { text: "", code: null };

const CODE_RE = /^[A-Za-z]{3}\+?$/;
const DEBOUNCE_MS = 250;
const MIN_CHARS = 2;

/**
 * The code to search with: the picked one, or a 3-letter code typed by hand
 * ("tlv" -> "TLV"). Empty string when neither: the form refuses to submit.
 */
export function resolveCode(value: AirportValue): string {
  if (value.code) return value.code;
  const typed = value.text.trim();
  return CODE_RE.test(typed) ? typed.toUpperCase() : "";
}

function optionLabel(location: Location): string {
  const place =
    location.sub_type === "CITY"
      ? location.name
      : `${location.name}${location.city_name && location.city_name !== location.name ? `, ${location.city_name}` : ""}`;
  return `${place} (${location.iata_code})`;
}

interface Props {
  label: string;
  value: AirportValue;
  onChange: (value: AirportValue) => void;
  placeholder?: string;
}

// Origin/destination box with suggestions from GET /api/locations. Typing waits
// DEBOUNCE_MS before asking, and the backend caches each keyword in Redis, so
// fast typing costs few provider calls.
export function AirportInput({ label, value, onChange, placeholder }: Props) {
  const [options, setOptions] = useState<Location[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();

  useEffect(() => {
    const keyword = value.text.trim();
    // A value with a code is already resolved (picked from the list, swapped in
    // from the other box, or filled by a deal): it needs no suggestions. Typing
    // sets the code back to null, so suggestions come back as soon as the user edits.
    if (keyword.length < MIN_CHARS || value.code !== null) {
      setOptions([]);
      setOpen(false);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchLocations(keyword, controller.signal)
        .then((results) => {
          setOptions(results);
          setActive(-1);
          setOpen(results.length > 0);
        })
        // Suggestions are a convenience: on any error the user can still type a code.
        .catch(() => setOptions([]));
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value.text, value.code]);

  function pick(location: Location) {
    onChange({
      text: optionLabel(location),
      code: location.search_code,
      // A CITY suggestion is the city itself; an AIRPORT one names its city.
      place: {
        city: location.city_name ?? location.name,
        country: location.country_name ?? "",
      },
    });
    setOpen(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open || options.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (event.key === "Enter" && active >= 0) {
      // Pick the highlighted option instead of submitting the form.
      event.preventDefault();
      pick(options[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="airport-field">
      <label>
        {label}
        <input
          value={value.text}
          onChange={(e) => onChange({ text: e.target.value, code: null })}
          onKeyDown={handleKeyDown}
          onFocus={() => setOpen(options.length > 0)}
          // Delay so a click on an option lands before the list closes.
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder}
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          required
        />
      </label>
      {open && (
        <ul className="suggestions" role="listbox" id={listId} aria-label={`${label} suggestions`}>
          {options.map((location, i) => (
            <li
              key={location.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              // mousedown, not click: it fires before the input's blur.
              onMouseDown={(e) => {
                e.preventDefault();
                pick(location);
              }}
            >
              <span className="badge">{location.sub_type === "CITY" ? "City" : "Airport"}</span>{" "}
              {optionLabel(location)}
              {location.country_name && <small> · {location.country_name}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
