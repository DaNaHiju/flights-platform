import { Fragment, useMemo, useState, type ReactNode } from "react";
import { formatPrice } from "./format";
import { dedupe, PAGE_SIZE, sortRanked, type Ranked, type SortKey } from "./results";

const TABS: { key: SortKey; label: string }[] = [
  { key: "best", label: "Best" },
  { key: "cheapest", label: "Cheapest" },
  { key: "fastest", label: "Fastest" },
];

interface Props<T> {
  results: Ranked<T>[];
  renderRow: (item: T) => ReactNode;
  // Distinguishes lists of one page (the legs of a multi-city trip).
  label?: string;
}

// Duplicates removed, a Best / Cheapest / Fastest tab bar (each tab shows the
// price of the offer that leads that view), "N results", and the first
// PAGE_SIZE rows with a "Show more" button for the rest.
export function ResultsList<T>({ results, renderRow, label = "Flight results" }: Props<T>) {
  const [sort, setSort] = useState<SortKey>("best");
  const [shown, setShown] = useState(PAGE_SIZE);

  const unique = useMemo(() => dedupe(results), [results]);
  const sorted = useMemo(() => {
    return {
      best: sortRanked(unique, "best"),
      cheapest: sortRanked(unique, "cheapest"),
      fastest: sortRanked(unique, "fastest"),
    };
  }, [unique]);

  if (unique.length === 0) return null;
  const list = sorted[sort];

  return (
    <div className="results-list">
      <div className="sort-bar">
        <div className="sort-tabs" role="group" aria-label={`Sort ${label}`}>
          {TABS.map(({ key, label: text }) => {
            const lead = sorted[key][0];
            return (
              <button
                key={key}
                type="button"
                className="sort-tab"
                aria-pressed={sort === key}
                onClick={() => {
                  setSort(key);
                  setShown(PAGE_SIZE);
                }}
              >
                <span>{text}</span>
                <small>{formatPrice(lead.price, lead.currency)}</small>
              </button>
            );
          })}
        </div>
        <p className="result-count">
          {unique.length} result{unique.length === 1 ? "" : "s"}
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
    </div>
  );
}
