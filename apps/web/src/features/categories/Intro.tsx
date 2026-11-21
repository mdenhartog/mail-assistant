import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";
import { Card } from "@/components/Card";
import { countText } from "@/features/categories/copy";

/** What a save does to mail (new mail only) and that the archive label is left alone. */
export function Intro(): ReactElement {
  return (
    <>
      <p className="text-text">When you save, new mail is filed using this list. Mail already filed stays where it is.</p>
      <Banner kind="info" title="Your archive label is left alone.">
        Mail you put in your archive label in Gmail is never re-sorted.
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
