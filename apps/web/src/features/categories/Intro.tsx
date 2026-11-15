import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";
import { Card } from "@/components/Card";
import { countText } from "@/features/categories/copy";

/** What a change does (R1: new mail only) and that Archive is left alone. */
export function Intro(): ReactElement {
  return (
    <>
      <div className="flex flex-col gap-2">
        <p className="text-text">Changes apply to new mail from now on. Old mail stays where it is for now.</p>
        <p className="text-sm text-text-muted">Renaming only changes the label name.</p>
      </div>
      <Banner kind="info" title="Archive is left alone.">
        Mail you put in the Gmail label Archive is never re-sorted.
      </Banner>
    </>
  );
}

/** The built-in "Other": mail that fits no category. It has no fields. */
export function OtherCard({ mailCount }: { mailCount: number }): ReactElement {
  return (
    <Card>
      <div aria-label="Other" className="flex flex-col gap-1" role="group">
        <h2 className="font-display text-xl text-text">Other</h2>
        <p className="text-text-muted">Mail that fits no category</p>
        <p className="text-sm text-text-muted">{countText(mailCount)}</p>
      </div>
    </Card>
  );
}
