import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";

/**
 * The banner of a 409: says who changed the settings and that nothing is saved yet.
 * It is the live region (`role="alert"`) and takes focus when it appears.
 *
 * @example
 * <ConflictBanner title="Settings changed in Telegram at 14:02 (Amsterdam time)." />
 */
export function ConflictBanner({ title }: { title: string }): ReactElement {
  return (
    <Banner focusOnMount kind="conflict" title={title}>
      I loaded the new values. Nothing is saved until you press Save again.
    </Banner>
  );
}
