// Google Flights search link with the route and dates already filled in.
//
// UNOFFICIAL: Google documents no URL format for this. The natural-language
// `q=` form below is what its own search box produces, and it can stop working
// without notice. If it does, the link still opens Google Flights, just empty.
export function googleFlightsUrl(
  origin: string,
  destination: string,
  date: string,
  returnDate?: string,
): string {
  const when = returnDate
    ? `on ${date} through ${returnDate}`
    : `on ${date} oneway`;
  const q = `Flights to ${destination} from ${origin} ${when}`;
  return `https://www.google.com/travel/flights?q=${encodeURIComponent(q)}`;
}
