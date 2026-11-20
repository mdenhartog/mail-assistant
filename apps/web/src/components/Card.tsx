import type { ReactElement, ReactNode } from "react";

/**
 * Raised surface that groups one setting or one category.
 *
 * @example
 * <Card><p>Quiet hours</p></Card>
 */
export function Card({ children }: { children: ReactNode }): ReactElement {
  return <div className="rounded-card bg-surface-raised p-5 shadow-soft">{children}</div>;
}
