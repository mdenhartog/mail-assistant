import type { ReactElement } from "react";

interface ZoneStatusProps {
  /** Result count for screen readers, e.g. "3 places found"; empty when nothing is listed. */
  announcement: string;
  /** The live local-time sentence. */
  live: string;
  savedValue: string;
}

/** Everything under the input that is not a hint: the hidden count, the stored zone, the live time and the key help. */
export function ZoneStatus({ announcement, live, savedValue }: ZoneStatusProps): ReactElement {
  return (
    <>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
      <p className="text-sm text-text-muted wrap-anywhere">{`Currently: ${savedValue}`}</p>
      <p aria-live="polite" className="text-sm text-text wrap-anywhere">
        {live}
      </p>
      <p className="text-sm text-text-muted">
        Type a city or a country, for example Bangkok. Escape closes the list; Escape again puts the saved zone back.
      </p>
    </>
  );
}
