import { useState, type ReactNode } from "react";
import { placeTitle } from "./destination";
import { useDestinationImage } from "./useDestinationImage";
import type { DestinationPlace } from "./types";

// Pixabay's terms: show the photographer and link to the photo's page.
function Credit({ user, url }: { user: string | null; url: string | null }) {
  const text = user ? `Photo: ${user} on Pixabay` : "Photo on Pixabay";
  if (!url) return <span className="photo-credit">{text}</span>;
  return (
    <a className="photo-credit" href={url} target="_blank" rel="noopener noreferrer">
      {text}
    </a>
  );
}

interface Props {
  city: string | null | undefined;
  country: string | null | undefined;
  alt: string;
  className: string;
  // Drawn over the photo (or over the gradient when there is none).
  children?: ReactNode;
}

/**
 * A box with the destination's photo and its credit. While the photo loads,
 * when there is none, and when the image fails to load, the box shows the brand
 * gradient instead.
 */
export function DestinationPhoto({ city, country, alt, className, children }: Props) {
  const photo = useDestinationImage(city, country);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const shown = photo.status === "ready" && photo.src !== failedSrc ? photo : null;

  return (
    <div className={`dest-photo ${className}${shown ? " has-photo" : ""}`}>
      {shown && (
        <>
          <img
            src={shown.src}
            alt={alt}
            loading="lazy"
            onError={() => setFailedSrc(shown.src)}
          />
          <Credit user={shown.creditUser} url={shown.creditUrl} />
        </>
      )}
      {children}
    </div>
  );
}

/** The strip above the search results: the photo with "City, Country" on it. */
export function DestinationBanner({ place }: { place: DestinationPlace }) {
  const title = placeTitle(place);
  return (
    <DestinationPhoto
      city={place.city}
      country={place.country}
      alt={`View of ${title}`}
      className="dest-banner"
    >
      <p className="dest-banner-name">{title}</p>
    </DestinationPhoto>
  );
}
