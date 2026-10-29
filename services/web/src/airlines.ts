// Airline website by IATA code, for the most common airlines on routes from TLV.
//
// `name` is the exact airline name flights-api sends (it comes from fli's airline
// table). The API sends names, not IATA codes, so lookups go through the name.
// A few fli names look odd: LH is "Lufthansa Cargo" and AZ is "Alitalia" (now ITA
// Airways); they are kept as fli spells them, because that is what arrives.
interface Airline {
  name: string;
  url: string;
}

export const AIRLINES: Record<string, Airline> = {
  LY: { name: "El Al", url: "https://www.elal.com" },
  "6H": { name: "Israir Airlines", url: "https://www.israir.co.il" },
  IZ: { name: "Arkia", url: "https://www.arkia.com" },
  LH: { name: "Lufthansa Cargo", url: "https://www.lufthansa.com" },
  OS: { name: "Austrian Airlines", url: "https://www.austrian.com" },
  LX: { name: "Swiss International Air Lines", url: "https://www.swiss.com" },
  TK: { name: "Turkish Airlines", url: "https://www.turkishairlines.com" },
  PC: { name: "Pegasus Airlines", url: "https://www.flypgs.com" },
  A3: { name: "Aegean Airlines", url: "https://en.aegeanair.com" },
  AF: { name: "Air France", url: "https://www.airfrance.com" },
  KL: { name: "KLM", url: "https://www.klm.com" },
  BA: { name: "British Airways", url: "https://www.britishairways.com" },
  IB: { name: "Iberia", url: "https://www.iberia.com" },
  UX: { name: "Air Europa", url: "https://www.aireuropa.com" },
  VY: { name: "Vueling", url: "https://www.vueling.com" },
  FR: { name: "Ryanair", url: "https://www.ryanair.com" },
  U2: { name: "easyJet", url: "https://www.easyjet.com" },
  W6: { name: "Wizz Air", url: "https://wizzair.com" },
  EK: { name: "Emirates", url: "https://www.emirates.com" },
  EY: { name: "Etihad Airways", url: "https://www.etihad.com" },
  FZ: { name: "flydubai", url: "https://www.flydubai.com" },
  QR: { name: "Qatar Airways", url: "https://www.qatarairways.com" },
  AC: { name: "Air Canada", url: "https://www.aircanada.com" },
  UA: { name: "United Airlines", url: "https://www.united.com" },
  DL: { name: "Delta Air Lines", url: "https://www.delta.com" },
  AA: { name: "American Airlines", url: "https://www.aa.com" },
  AZ: { name: "Alitalia", url: "https://www.ita-airways.com" },
  LO: { name: "LOT Polish Airlines", url: "https://www.lot.com" },
  OK: { name: "Czech Airlines", url: "https://www.csa.cz" },
  TP: { name: "TAP Portugal", url: "https://www.flytap.com" },
  SN: { name: "Brussels Airlines", url: "https://www.brusselsairlines.com" },
  SK: { name: "Scandinavian Airlines", url: "https://www.flysas.com" },
  AY: { name: "Finnair", url: "https://www.finnair.com" },
  ET: { name: "Ethiopian Airlines", url: "https://www.ethiopianairlines.com" },
};

const URL_BY_NAME = new Map(
  Object.values(AIRLINES).map((airline) => [airline.name, airline.url]),
);

/** Website of the airline with this name, or undefined when it is not in the map. */
export function airlineUrl(name: string): string | undefined {
  return URL_BY_NAME.get(name);
}
