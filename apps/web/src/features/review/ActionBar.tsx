import { useEffect, useRef, useState } from "react";
import type { ReactElement, RefObject } from "react";

import { Button } from "@/components/Button";
import { moveLabel } from "@/features/review/copy";

/** Room left above the bar for the focus ring of the box that is scrolled into view. */
const BREATHING_PX = 8;
/** The bar sticks only while it takes up at most this share (one in N) of the window. */
const MAX_SHARE = 3;

/**
 * True while the bar is small enough to stick to the bottom of the window. With large text in a small window it
 * would cover the mails, so it stays in the page flow instead. While it sticks, the page scrolls a focused box
 * clear of it (scroll padding of the bar height), so the bar never hides the box that has focus.
 */
function useSticksToBottom(ref: RefObject<HTMLElement | null>): boolean {
  const [sticky, setSticky] = useState(false);
  useEffect(() => {
    const bar = ref.current;
    const root = document.documentElement;
    if (bar === null) {
      return undefined;
    }
    const measure = (): void => {
      const height = bar.offsetHeight;
      const fits = height * MAX_SHARE <= window.innerHeight;
      setSticky(fits);
      if (fits) {
        root.style.setProperty("scroll-padding-bottom", `${String(height + BREATHING_PX)}px`);
      } else {
        root.style.removeProperty("scroll-padding-bottom");
      }
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(bar);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      root.style.removeProperty("scroll-padding-bottom");
    };
  }, [ref]);
  return sticky;
}

export interface ActionBarProps {
  approved: number;
  undecided: number;
  onMove: () => void;
}

/**
 * The bar at the bottom of the review: the one button says what it does ("Move 80 mails, labels only"). With nothing
 * approved it stays in place but does nothing, and the text next to it says why. The page keeps scroll padding for it
 * (`useSticksToBottom`), so it never covers the box that has focus.
 */
export function ActionBar({ approved, undecided, onMove }: ActionBarProps): ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const sticky = useSticksToBottom(ref);
  return (
    <div
      className="data-sticky:sticky bottom-0 z-10 -mx-6 mt-6 flex flex-col gap-3 border-t border-divider bg-surface-raised px-6 py-3 sm:flex-row sm:items-center sm:justify-between"
      data-action-bar=""
      data-sticky={sticky ? "true" : undefined}
      ref={ref}
    >
      <p className="min-w-0 text-text wrap-anywhere">
        {approved === 0
          ? "Approve a group or tick mails first. Nothing moves until you confirm."
          : `${String(undecided)} not decided yet stay where they are.`}
      </p>
      <Button disabled={approved === 0} onClick={onMove} variant="primary">
        {moveLabel(approved)}
      </Button>
    </div>
  );
}
