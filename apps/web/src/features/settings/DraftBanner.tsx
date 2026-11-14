import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";

/**
 * After sign-in: the values typed before the session ended are back in the form. A polite status,
 * not an alert; nothing was saved and nothing is saved until Marco presses Save.
 *
 * @example
 * {flow.restored ? <DraftBanner /> : null}
 */
export function DraftBanner(): ReactElement {
  return (
    <Banner kind="info" title="Welcome back.">
      Your unsaved changes are restored. Check them and save.
    </Banner>
  );
}
