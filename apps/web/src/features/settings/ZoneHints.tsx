import type { ReactElement } from "react";

interface ZoneHintsProps {
  id: string;
  typed: string;
  noMatch: boolean;
  lookupFailed: boolean;
  suggestion: string | null;
  onSuggest: (text: string) => void;
}

/** The quiet messages under the input. None is an alert: unknown text is a hint, not an error. */
export function ZoneHints({ id, typed, noMatch, lookupFailed, suggestion, onSuggest }: ZoneHintsProps): ReactElement | null {
  if (lookupFailed) {
    return (
      <p className="text-sm text-text-muted" id={id}>
        I could not look that up just now. Keep typing or try again in a moment.
      </p>
    );
  }
  if (!noMatch) {
    return null;
  }
  return (
    <p className="text-sm text-text-muted" id={id}>
      {`Nothing found for '${typed}'. Try the nearest bigger city, or the country.`}
      {suggestion ? (
        <>
          {" "}
          <button
            className="min-h-11 font-semibold text-primary underline"
            onClick={() => {
              onSuggest(suggestion);
            }}
            onMouseDown={(event) => {
              event.preventDefault();
            }}
            type="button"
          >
            {`Did you mean ${suggestion}?`}
          </button>
        </>
      ) : null}
    </p>
  );
}
