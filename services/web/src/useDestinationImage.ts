import { useEffect, useState } from "react";
import { getDestinationImage } from "./api";

export type DestinationPhotoState =
  | { status: "loading" }
  // No photo: none exists, the backend has no key, or the request failed.
  | { status: "none" }
  | { status: "ready"; src: string; creditUser: string | null; creditUrl: string | null };

const LOADING: DestinationPhotoState = { status: "loading" };
const NONE: DestinationPhotoState = { status: "none" };

/**
 * The photo of "<city>, <country>" from /api/destination-image. Every failure
 * ends in "none": a photo is decoration, so the page keeps its gradient.
 */
export function useDestinationImage(
  city: string | null | undefined,
  country: string | null | undefined,
): DestinationPhotoState {
  // The state remembers which place it answers for, so a new place never shows
  // the previous photo while its own is loading.
  const [answer, setAnswer] = useState<{ for: string; state: DestinationPhotoState } | null>(null);
  const wanted = city ? `${city}|${country ?? ""}` : "";

  useEffect(() => {
    if (!city) return;
    const controller = new AbortController();
    getDestinationImage(city, country ?? "", controller.signal)
      .then((image) => {
        const state: DestinationPhotoState =
          image.available && image.url
            ? {
                status: "ready",
                src: image.url,
                creditUser: image.credit_user,
                creditUrl: image.credit_url,
              }
            : NONE;
        setAnswer({ for: wanted, state });
      })
      .catch(() => {
        if (!controller.signal.aborted) setAnswer({ for: wanted, state: NONE });
      });
    return () => controller.abort();
  }, [city, country, wanted]);

  if (!wanted) return NONE;
  return answer?.for === wanted ? answer.state : LOADING;
}
