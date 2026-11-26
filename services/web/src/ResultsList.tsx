import { Fragment, useId, useMemo, useState, type ReactNode } from "react";
import { formatPrice } from "./format";
import {
  activeFilterCount,
  applyFilters,
  buildFacets,
  dedupe,
  NO_FILTERS,
  PAGE_SIZE,
  SORT_OPTIONS,
  sortRanked,
  STOPS_BUCKETS,
  TIME_BUCKETS,
  type Facets,
  type Filters,
  type Ranked,
  type SortKey,
} from "./results";

// The three quick tabs; the "Sort by" menu offers them too, plus three more.
const TABS: { key: SortKey; label: string }[] = [
  { key: "best", label: "Best" },
  { key: "cheapest", label: "Cheapest" },
  { key: "fastest", label: "Fastest" },
];

// Adds the value if it is missing, removes it if it is there.
function toggle<V>(list: V[], value: V): V[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

interface PanelProps {
  id: string;
  open: boolean;
  facets: Facets;
  filters: Filters;
  shown: number;
  total: number;
  onChange: (next: Filters) => void;
}

// The filters of one list. Always in the DOM: on a phone CSS hides it until the
// "Filters" button opens it, on a desktop it is a column beside the list.
function FilterPanel({ id, open, facets, filters, shown, total, onChange }: PanelProps) {
  const active = activeFilterCount(filters) > 0;
  const priceValue = filters.maxPrice ?? facets.maxPrice;
  const hoursValue = filters.maxDurationHours ?? facets.maxHours;

  return (
    <aside className={`filters${open ? " open" : ""}`} id={id} aria-label="Filters">
      <p className="filters-count" role="status">
        Showing {shown} of {total}
      </p>

      <fieldset>
        <legend>Stops</legend>
        {STOPS_BUCKETS.map(({ key, label }) => (
          <label key={key} className="check">
            <input
              type="checkbox"
              checked={filters.stops.includes(key)}
              onChange={() => onChange({ ...filters, stops: toggle(filters.stops, key) })}
            />
            <span>{label}</span>
            <small>{facets.stopCounts[key]}</small>
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>Airlines</legend>
        {facets.airlines.map((airline) => (
          <label key={airline} className="check">
            <input
              type="checkbox"
              checked={filters.airlines.includes(airline)}
              onChange={() => onChange({ ...filters, airlines: toggle(filters.airlines, airline) })}
            />
            <span>{airline}</span>
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>Departure time</legend>
        {TIME_BUCKETS.map(({ key, label }) => (
          <label key={key} className="check">
            <input
              type="checkbox"
              checked={filters.times.includes(key)}
              onChange={() => onChange({ ...filters, times: toggle(filters.times, key) })}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>

      <div className="slider">
        <div className="slider-head">
          <label htmlFor={`${id}-price`}>Max price</label>
          <output htmlFor={`${id}-price`}>{formatPrice(priceValue, facets.currency)}</output>
        </div>
        <input
          id={`${id}-price`}
          type="range"
          min={facets.minPrice}
          max={facets.maxPrice}
          step={1}
          value={priceValue}
          disabled={facets.minPrice >= facets.maxPrice}
          // At the far end nothing is left out, so it is "no limit" again.
          onChange={(e) =>
            onChange({ ...filters, maxPrice: +e.target.value >= facets.maxPrice ? null : +e.target.value })
          }
        />
      </div>

      <div className="slider">
        <div className="slider-head">
          <label htmlFor={`${id}-duration`}>Max duration</label>
          <output htmlFor={`${id}-duration`}>{hoursValue}h</output>
        </div>
        <input
          id={`${id}-duration`}
          type="range"
          min={facets.minHours}
          max={facets.maxHours}
          step={1}
          value={hoursValue}
          disabled={facets.minHours >= facets.maxHours}
          onChange={(e) =>
            onChange({
              ...filters,
              maxDurationHours: +e.target.value >= facets.maxHours ? null : +e.target.value,
            })
          }
        />
      </div>

      <button type="button" className="clear-filters" disabled={!active} onClick={() => onChange(NO_FILTERS)}>
        Clear filters
      </button>
    </aside>
  );
}

interface Props<T> {
  results: Ranked<T>[];
  renderRow: (item: T) => ReactNode;
  // Distinguishes lists of one page (the legs of a multi-city trip).
  label?: string;
}

// Duplicates removed, then the filters (panel beside the list, "Filters" button
// on a phone), a Best / Cheapest / Fastest tab bar (each tab shows the price of
// the offer that leads that view), a "Sort by" menu that shares its state with
// the tabs, "N results", and the first PAGE_SIZE rows with a "Show more" button
// for the rest. Everything runs in the browser on the results already fetched.
export function ResultsList<T>({ results, renderRow, label = "Flight results" }: Props<T>) {
  const [sort, setSort] = useState<SortKey>("best");
  const [shown, setShown] = useState(PAGE_SIZE);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [panelOpen, setPanelOpen] = useState(false);
  const sortId = useId();
  const panelId = useId();

  const unique = useMemo(() => dedupe(results), [results]);
  const facets = useMemo(() => (unique.length > 0 ? buildFacets(unique) : null), [unique]);
  const filtered = useMemo(() => applyFilters(unique, filters), [unique, filters]);
  const sorted = useMemo(() => {
    return {
      best: sortRanked(filtered, "best"),
      cheapest: sortRanked(filtered, "cheapest"),
      fastest: sortRanked(filtered, "fastest"),
    };
  }, [filtered]);
  const list = useMemo(
    () => (sort in sorted ? sorted[sort as keyof typeof sorted] : sortRanked(filtered, sort)),
    [sort, sorted, filtered],
  );

  if (unique.length === 0 || !facets) return null;

  function changeSort(key: SortKey) {
    setSort(key);
    setShown(PAGE_SIZE);
  }

  function changeFilters(next: Filters) {
    setFilters(next);
    setShown(PAGE_SIZE);
  }

  const activeCount = activeFilterCount(filters);

  return (
    <div className="results-list">
      <button
        type="button"
        className="filters-toggle"
        aria-expanded={panelOpen}
        aria-controls={panelId}
        onClick={() => setPanelOpen(!panelOpen)}
      >
        Filters{activeCount > 0 ? ` (${activeCount})` : ""}
      </button>
      <div className="results-layout">
        <FilterPanel
          id={panelId}
          open={panelOpen}
          facets={facets}
          filters={filters}
          shown={filtered.length}
          total={unique.length}
          onChange={changeFilters}
        />
        <div className="results-main">
          {filtered.length === 0 ? (
            <div className="no-matches">
              <p className="status">No flights match your filters.</p>
              <button type="button" className="clear-filters" onClick={() => changeFilters(NO_FILTERS)}>
                Clear filters
              </button>
            </div>
          ) : (
            <>
              <div className="sort-bar">
                <div className="sort-tabs" role="group" aria-label={`Sort ${label}`}>
                  {TABS.map(({ key, label: text }) => {
                    const lead = sorted[key as keyof typeof sorted][0];
                    return (
                      <button
                        key={key}
                        type="button"
                        className="sort-tab"
                        aria-pressed={sort === key}
                        onClick={() => changeSort(key)}
                      >
                        <span>{text}</span>
                        <small>{formatPrice(lead.price, lead.currency)}</small>
                      </button>
                    );
                  })}
                </div>
                <label className="sort-select" htmlFor={sortId}>
                  Sort by
                  <select id={sortId} value={sort} onChange={(e) => changeSort(e.target.value as SortKey)}>
                    {SORT_OPTIONS.map(({ key, label: text }) => (
                      <option key={key} value={key}>
                        {text}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="result-count">
                  {filtered.length} result{filtered.length === 1 ? "" : "s"}
                </p>
              </div>
              <ul className="offers" aria-label={label}>
                {list.slice(0, shown).map((r) => (
                  <Fragment key={r.key}>{renderRow(r.item)}</Fragment>
                ))}
              </ul>
              {shown < list.length && (
                <button type="button" className="show-more" onClick={() => setShown(shown + PAGE_SIZE)}>
                  Show more
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
