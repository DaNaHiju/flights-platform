import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { displayCode, formatPrice, localTime } from "./format";
import { FlightRow } from "./FlightRow";
import {
  groupByOutbound,
  rankGroup,
  rankOneWay,
  rankReturn,
  type OutboundGroup,
} from "./results";
import { ResultsList } from "./ResultsList";
import type { FlightOffer, RoundTripOffer } from "./types";

// ── Steps ────────────────────────────────────────────────────────────────────
// Every trip type is a list of steps ending in a review. `picks[i]` is what was
// chosen at step i; going back to step i forgets that choice and the later ones.

function useSteps<P>() {
  const [step, setStep] = useState(0);
  const [picks, setPicks] = useState<P[]>([]);
  return {
    step,
    picks,
    choose(pick: P) {
      setPicks([...picks.slice(0, step), pick]);
      setStep(step + 1);
    },
    back(to: number) {
      setPicks(picks.slice(0, to));
      setStep(to);
    },
  };
}

interface ShellProps {
  labels: string[];
  current: number;
  // What was chosen at each finished step, shown next to its "Change" button.
  summaries: string[];
  onChange: (step: number) => void;
  children: ReactNode;
}

// "1 Outbound · 2 Return · 3 Review", with the choice made at each finished step.
function Shell({ labels, current, summaries, onChange, children }: ShellProps) {
  const top = useRef<HTMLDivElement>(null);
  const first = useRef(true);

  // A new step starts at the top of its list. Not on the first render, where
  // the page already scrolls to the results. Optional call: jsdom lacks it.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    top.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [current]);

  return (
    <div className="flow" ref={top}>
      <ol className="steps" aria-label="Steps">
        {labels.map((label, i) => (
          <li
            key={label}
            className={i < current ? "done" : i === current ? "current" : undefined}
            aria-current={i === current ? "step" : undefined}
          >
            <span className="step-head">
              <span className="step-num">{i + 1}</span>
              <span className="step-label">{label}</span>
            </span>
            {i < current && (
              <span className="step-choice">
                <span>{summaries[i]}</span>
                <button type="button" onClick={() => onChange(i)} aria-label={`Change ${label}`}>
                  Change
                </button>
              </span>
            )}
          </li>
        ))}
      </ol>
      {children}
    </div>
  );
}

// "ITA Airways, ANA · 08:00 → 10:05 · TLV → HND"
function describe(offer: FlightOffer, price?: string): string {
  const start = offer.legs[0];
  const end = offer.legs[offer.legs.length - 1];
  const airlines = [...new Set(offer.legs.map((l) => l.airline))].join(", ") || offer.primary_airline;
  const parts = [airlines];
  if (start && end) {
    parts.push(`${localTime(start.departure_datetime)} → ${localTime(end.arrival_datetime)}`);
    if (start.departure_airport_code && end.arrival_airport_code) {
      parts.push(`${start.departure_airport_code} → ${end.arrival_airport_code}`);
    }
  }
  if (price) parts.push(price);
  return parts.join(" · ");
}

function Review({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="review">
      <h3 className="leg-title">{title}</h3>
      {children}
    </div>
  );
}

// ── One way: Choose -> Review ───────────────────────────────────────────────

export function OneWayFlow({ offers, adults = 1 }: { offers: FlightOffer[]; adults?: number }) {
  const { step, picks, choose, back } = useSteps<FlightOffer>();
  const ranked = useMemo(() => offers.map(rankOneWay), [offers]);
  const pick = picks[0];

  return (
    <Shell
      labels={["Flight", "Review"]}
      current={step}
      summaries={pick ? [describe(pick, formatPrice(pick.price, pick.currency))] : []}
      onChange={back}
    >
      {step === 0 && (
        <ResultsList
          results={ranked}
          renderRow={(offer) => (
            <FlightRow
              travelers={adults}
              directions={[{ offer }]}
              price={offer.price}
              currency={offer.currency}
              onChoose={() => choose(offer)}
            />
          )}
        />
      )}
      {step === 1 && pick && (
        <Review title="Review your flight">
          <ul className="offers" aria-label="Your flight">
            <FlightRow
              travelers={adults}
              review
              directions={[{ offer: pick }]}
              price={pick.price}
              currency={pick.currency}
              deepLink={pick.deep_link}
            />
          </ul>
        </Review>
      )}
    </Shell>
  );
}

// ── Round trip: outbound -> return (only those sold with it) -> Review ──────

export function RoundTripFlow({ offers, adults = 1 }: { offers: RoundTripOffer[]; adults?: number }) {
  const { step, picks, choose, back } = useSteps<OutboundGroup | RoundTripOffer>();
  const groups = useMemo(() => groupByOutbound(offers).map(rankGroup), [offers]);
  const group = picks[0] as OutboundGroup | undefined;
  const pair = picks[1] as RoundTripOffer | undefined;
  const returns = useMemo(() => (group ? group.pairs.map(rankReturn) : []), [group]);

  const summaries: string[] = [];
  if (group) summaries.push(describe(group.outbound));
  if (pair) summaries.push(describe(pair.return, formatPrice(pair.price, pair.currency)));

  return (
    <Shell labels={["Outbound", "Return", "Review"]} current={step} summaries={summaries} onChange={back}>
      {step === 0 && (
        <ResultsList
          label="Outbound flights"
          results={groups}
          renderRow={(g) => (
            <FlightRow
              travelers={adults}
              directions={[{ offer: g.outbound }]}
              price={g.minPrice}
              currency={g.currency}
              pricePrefix="from"
              caption={`${g.pairs.length} return option${g.pairs.length === 1 ? "" : "s"}`}
              onChoose={() => choose(g)}
            />
          )}
        />
      )}
      {step === 1 && group && (
        <ResultsList
          label="Return flights"
          results={returns}
          renderRow={(p) => (
            <FlightRow
              travelers={adults}
              directions={[{ offer: p.return }]}
              price={p.price}
              currency={p.currency}
              caption="total, round trip"
              onChoose={() => choose(p)}
            />
          )}
        />
      )}
      {step === 2 && pair && (
        <Review title="Review your trip">
          <ul className="offers" aria-label="Your trip">
            <FlightRow
              travelers={adults}
              review
              directions={[
                { label: "Outbound", offer: pair.outbound },
                { label: "Return", offer: pair.return },
              ]}
              price={pair.price}
              currency={pair.currency}
              deepLink={pair.deep_link}
            />
          </ul>
        </Review>
      )}
    </Shell>
  );
}

// ── Multi-city: flight 1 -> flight 2 -> Review (two separate tickets) ───────

// One leg of a multi-city trip. Each leg is searched on its own, so one can fail
// (e.g. the provider answers 502) while the other still has results.
export interface LegSearch {
  origin: string;
  destination: string;
  date: string;
  offers?: FlightOffer[];
  error?: string;
}

function LegStep({
  index,
  leg,
  adults,
  onChoose,
}: {
  index: number;
  leg: LegSearch;
  adults: number;
  onChoose: (offer: FlightOffer) => void;
}) {
  const ranked = useMemo(() => (leg.offers ?? []).map(rankOneWay), [leg.offers]);
  return (
    <div>
      <h3 className="leg-title">
        Leg {index + 1}: {displayCode(leg.origin)} → {displayCode(leg.destination)} · {leg.date}
      </h3>
      {leg.error && <p role="alert">{leg.error}</p>}
      {leg.offers?.length === 0 && <p className="status">No flights found for this leg.</p>}
      <ResultsList
        label={`Flights, leg ${index + 1}`}
        results={ranked}
        renderRow={(offer) => (
          <FlightRow
            travelers={adults}
            directions={[{ offer }]}
            price={offer.price}
            currency={offer.currency}
            onChoose={() => onChoose(offer)}
          />
        )}
      />
    </div>
  );
}

export function MultiCityFlow({ legs, adults = 1 }: { legs: LegSearch[]; adults?: number }) {
  const { step, picks, choose, back } = useSteps<FlightOffer>();

  const total =
    picks.length === 2 && new Set(picks.map((p) => p.currency)).size === 1
      ? picks[0].price + picks[1].price
      : null;

  return (
    <Shell
      labels={["Flight 1", "Flight 2", "Review"]}
      current={step}
      summaries={picks.map((p) => describe(p, formatPrice(p.price, p.currency)))}
      onChange={back}
    >
      {step < 2 && <LegStep key={step} index={step} leg={legs[step]} adults={adults} onChoose={choose} />}
      {step === 2 && (
        <Review title="Review your trip">
          <p className="tickets">
            <span className="tl-badge">2 tickets</span>
            {total !== null && (
              <strong className="total-price">
                Total: {formatPrice(total, picks[0].currency)}
                {adults > 1 && <small> for {adults} travelers</small>}
              </strong>
            )}
          </p>
          <p className="notice">
            Separate bookings: if flight 1 is delayed, airline 2 won&apos;t wait for you.
          </p>
          {picks.map((p, i) => (
            <div key={i} className="ticket">
              <h4>Ticket {i + 1}</h4>
              <ul className="offers" aria-label={`Ticket ${i + 1}`}>
                <FlightRow
                  travelers={adults}
                  review
                  bookLabel={`Book ticket ${i + 1}`}
                  directions={[{ offer: p }]}
                  price={p.price}
                  currency={p.currency}
                  deepLink={p.deep_link}
                />
              </ul>
            </div>
          ))}
        </Review>
      )}
    </Shell>
  );
}
