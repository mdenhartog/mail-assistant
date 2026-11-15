import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";
import type { SaveResult } from "@/features/categories/useCategoriesSave";

/** The banner for what the last save left behind; blocking ones take focus so a keyboard user hears them. */
export function SaveResultBanner({ result, onRetry }: { result: SaveResult; onRetry: () => void }): ReactElement | null {
  switch (result) {
    case "saved":
      return (
        <Banner focusOnMount kind="success" title="Saved.">
          Your list applies to new mail from now on.
        </Banner>
      );
    case "conflict":
      return (
        <Banner focusOnMount kind="conflict" title="The list changed somewhere else.">
          This is the newest list. Your changes were not saved; make them again.
        </Banner>
      );
    case "rate-limited":
      return (
        <Banner focusOnMount kind="danger" title="Too many saves.">
          Wait a minute and try again.
        </Banner>
      );
    case "refused":
      return (
        <Banner focusOnMount kind="danger" title="Some values were not accepted.">
          Check the list and try again.
        </Banner>
      );
    case "failed":
      return (
        <Banner
          action={{ label: "Try again", onClick: onRetry }}
          focusOnMount
          kind="danger"
          title="Could not save. Nothing was changed."
        >
          Check your connection and try again.
        </Banner>
      );
    case null:
      return null;
  }
}
