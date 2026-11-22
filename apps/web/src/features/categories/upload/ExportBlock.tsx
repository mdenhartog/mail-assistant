import type { ReactElement } from "react";

import { useExportText } from "@/api/categories/upload.queries";
import { Button } from "@/components/Button";
import { useCopy } from "@/features/categories/upload/useCopy";

const LINK = "inline-flex min-h-11 items-center font-semibold text-primary underline wrap-anywhere";

/** Export (download or copy) and the template and example files. */
export function ExportBlock(): ReactElement {
  const exported = useExportText();
  const { status, copy } = useCopy();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <a className={LINK} download="mail-categories.yaml" href="/api/categories/export">
          Download my list
        </a>
        <Button
          onClick={() => {
            void copy(() => exported.mutateAsync());
          }}
        >
          Copy my list
        </Button>
      </div>
      <p role="status" className="text-text-muted">
        {status === "copied" ? "Copied." : status === "failed" ? "Could not copy your list." : ""}
      </p>
      <p className="text-text-muted">New to the format? Start from a commented file.</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <a className={LINK} download href="/api/categories/template?file=template">
          Download the template
        </a>
        <a className={LINK} download href="/api/categories/template?file=example">
          Download the example
        </a>
      </div>
    </div>
  );
}
