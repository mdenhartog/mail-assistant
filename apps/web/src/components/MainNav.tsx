import { NavLink } from "react-router";
import type { ReactElement } from "react";

import { paths } from "@/router/paths";

export interface MainNavProps {
  /** Review items waiting; the badge is left out for zero or when unknown. */
  openItems?: number | undefined;
}

const LINK = "inline-flex min-h-11 items-center gap-2 rounded-pill border-2 px-4 font-semibold text-text ";
const LINK_IDLE = LINK + "border-transparent";
const LINK_CURRENT = LINK + "border-primary bg-surface-raised";

/**
 * Main navigation of the signed-in pages: Settings, Categories and Review moves. The current page
 * carries `aria-current="page"`; the badge is read as "<n> open items" and its digits are hidden
 * from a screen reader so the count is not announced twice.
 *
 * @example
 * <MainNav openItems={842} />
 */
export function MainNav({ openItems }: MainNavProps): ReactElement {
  const items = [
    { to: paths.settings, label: "Settings" },
    { to: paths.categories, label: "Categories" },
    { to: paths.review, label: "Review moves" },
  ];
  return (
    <nav aria-label="Main" className="border-b border-divider px-6 py-2">
      <ul className="flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink className={({ isActive }) => (isActive ? LINK_CURRENT : LINK_IDLE)} to={item.to}>
              {item.label}
              {item.to === paths.review && openItems !== undefined && openItems > 0 ? (
                <>
                  {" "}
                  <span
                    aria-hidden="true"
                    className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-pill bg-primary px-2 text-sm text-primary-contrast"
                  >
                    {openItems}
                  </span>
                  <span className="sr-only">{`${String(openItems)} open items`}</span>
                </>
              ) : null}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
