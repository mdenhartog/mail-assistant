import type { ReactElement } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { Banner } from "@/components/Banner";
import { DropZone } from "@/features/categories/upload/DropZone";
import { ExportBlock } from "@/features/categories/upload/ExportBlock";
import { PreviewPanel } from "@/features/categories/upload/PreviewPanel";
import { ProblemsPanel } from "@/features/categories/upload/ProblemsPanel";
import { UploadNotice } from "@/features/categories/upload/UploadNotice";
import { useUploadFlow } from "@/features/categories/upload/useUploadFlow";
import type { UploadFlow } from "@/features/categories/upload/useUploadFlow";

function Outcome({ flow }: { flow: UploadFlow }): ReactElement | null {
  const { phase } = flow;
  switch (phase.kind) {
    case "checking":
      return <p role="status">Checking your file.</p>;
    case "preview":
      return <PreviewPanel busy={flow.replacing} onCancel={flow.cancel} onReplace={flow.replace} preview={phase.preview} />;
    case "refused":
      return <ProblemsPanel problems={phase.problems} />;
    case "notice":
      return <UploadNotice notice={phase.notice} />;
    case "replaced":
      return (
        <Banner action={{ label: "Restore previous version", onClick: flow.restore }} kind="success" title="Your list was replaced.">
          New mail follows it from now on. Mail already filed stays where it is.
        </Banner>
      );
    case "restoring":
      return <Banner kind="info" title="Restoring the previous version." />;
    case "restored":
      return (
        <Banner kind="success" title="The previous version is back.">
          Your list is the one from before the upload.
        </Banner>
      );
    default:
      return null;
  }
}

/** Replace the whole list from a YAML file after a preview, restore the previous version, export, and the template. */
export function UploadSection({ list }: { list: CategoryList }): ReactElement {
  const flow = useUploadFlow(list.version);
  const busy = flow.phase.kind === "checking" || flow.phase.kind === "restoring" || flow.replacing;
  return (
    <section aria-labelledby="import-export" className="mt-10 flex flex-col gap-4 border-t border-divider pt-8">
      <h2 className="font-display text-xl text-text wrap-anywhere" id="import-export">
        Import and export
      </h2>
      <p className="text-text">Replace the whole list from a YAML file, or keep your list as a file.</p>
      <DropZone disabled={busy} onFile={flow.choose} />
      <Outcome flow={flow} />
      <ExportBlock />
    </section>
  );
}
