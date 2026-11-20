import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { countText } from "@/features/review/copy";

const PAUSE_MS = 400;

/**
 * The one polite live region of the page for the selection count. The text follows the count after a short
 * pause, so ticking ten boxes quickly is announced once, not ten times (AC-23). Nothing is said for zero.
 */
export function SelectionLive({ count }: { count: number }): ReactElement {
  const [text, setText] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setText(count === 0 ? "" : `${countText(count)} selected`);
    }, PAUSE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [count]);
  return (
    <p aria-atomic="true" aria-live="polite" className="sr-only">
      {text}
    </p>
  );
}
