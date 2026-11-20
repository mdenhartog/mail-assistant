import { useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode, RefObject } from "react";

/** Room left above the bar for the focus ring of the box that is scrolled into view. */
const BREATHING_PX = 8;
/** The bar sticks only while it takes up at most this share (one in N) of the window. */
const MAX_SHARE = 3;

/**
 * True while the bar is small enough to stick to the bottom of the window. With large text in a small window it
 * would cover the page, so it stays in the page flow instead. While it sticks, the page scrolls a focused box
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

/**
 * The bar at the bottom of a page that holds its main action (save, move). It sticks to the bottom of the window only
 * while it fits, and it carries the `data-action-bar` mark that the layout checks use to know that content scrolls
 * under it on purpose. `className` adds the layout of the inside; the bar's own look is fixed here.
 */
export function StickyBar({ children, className = "" }: { children: ReactNode; className?: string }): ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const sticky = useSticksToBottom(ref);
  return (
    <div
      className={`data-sticky:sticky bottom-0 z-10 -mx-6 border-t border-divider bg-surface-raised px-6 py-3 ${className}`}
      data-action-bar=""
      data-sticky={sticky ? "true" : undefined}
      ref={ref}
    >
      {children}
    </div>
  );
}
