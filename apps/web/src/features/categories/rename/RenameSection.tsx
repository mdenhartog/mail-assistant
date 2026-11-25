import { useState } from "react";
import type { ReactElement } from "react";

import { useRenamePreview } from "@/api/categories/rename.queries";
import type { RenameFailure, RenamePreview as Preview } from "@/api/categories/rename.types";
import { Banner } from "@/components/Banner";
import { RENAME } from "@/features/categories/rename/copy";
import { RenamePreview } from "@/features/categories/rename/RenamePreview";
import { RenameResult } from "@/features/categories/rename/RenameResult";

type State = Preview["state"];

/** True once the state went from pending or confirmed to done while this page was open: only then the result takes the focus. */
function useFinishedNow(state: State | undefined): boolean {
  const [previous, setPrevious] = useState<State | undefined>(state);
  const [finished, setFinished] = useState(false);
  if (state !== previous) {
    setPrevious(state);
    if (state === "done" && (previous === "pending" || previous === "confirmed")) {
      setFinished(true);
    }
  }
  return finished;
}

function Loading(): ReactElement {
  return (
    <div aria-busy="true">
      <p className="text-text-muted" role="status">
        {RENAME.loading}
      </p>
      <div aria-hidden="true" className="mt-3 grid gap-4 sm:grid-cols-2">
        {[0, 1].map((card) => (
          <div className="h-40 rounded-card bg-divider motion-safe:animate-pulse" data-skeleton="" key={card} />
        ))}
      </div>
    </div>
  );
}

function Frame({ children }: { children: ReactElement | ReactElement[] }): ReactElement {
  return (
    <section aria-labelledby="rename-labels" className="mt-10 flex flex-col gap-4 border-t border-divider pt-8">
      <h2 className="font-display text-xl text-text wrap-anywhere" id="rename-labels">
        {RENAME.title}
      </h2>
      {children}
    </section>
  );
}

interface BodyProps {
  plan: Preview;
  failure: RenameFailure | null;
  onFailure: (failure: RenameFailure | null) => void;
  finishedNow: boolean;
}

/** What a plan shows: the preview, the running status or the result; `null` when there is nothing to show. */
function PlanBody({ plan, failure, onFailure, finishedNow }: BodyProps): ReactElement | null {
  const hasPlan = plan.items.length > 0;
  if (plan.state === "pending" && hasPlan) {
    return (
      <Frame>
        <RenamePreview failure={failure} key={plan.planHash} onFailure={onFailure} preview={plan} />
      </Frame>
    );
  }
  if (plan.state === "confirmed") {
    return (
      <Frame>
        <p aria-label={RENAME.inProgress} className="text-text" role="status">
          {RENAME.inProgress}. {RENAME.inProgressBody}
        </p>
      </Frame>
    );
  }
  if (plan.state === "done" && hasPlan) {
    return (
      <Frame>
        <RenameResult focusOnMount={finishedNow} preview={plan} />
      </Frame>
    );
  }
  return null;
}

function FirstRun(): ReactElement {
  return (
    <div className="mt-10">
      <Banner kind="info" title={RENAME.empty}>
        {RENAME.emptyHelp}
      </Banner>
    </div>
  );
}

/**
 * The one-time rename of the old prefixed labels. Nothing shows while there is no plan, except the first-run empty
 * state when the user has no list yet; a pending plan shows the preview, a running one a status, a finished one the result.
 */
export function RenameSection({ hasList }: { hasList: boolean }): ReactElement | null {
  const preview = useRenamePreview();
  const finishedNow = useFinishedNow(preview.data?.state);
  const [failure, setFailure] = useState<RenameFailure | null>(null);

  if (preview.isPending) {
    return (
      <Frame>
        <Loading />
      </Frame>
    );
  }
  if (preview.isError) {
    return (
      <Frame>
        <Banner
          action={{
            label: RENAME.tryAgain,
            onClick: () => {
              void preview.refetch();
            },
          }}
          kind="danger"
          title={RENAME.loadFailed}
        >
          {RENAME.checkConnection}
        </Banner>
      </Frame>
    );
  }
  if (preview.data.state === "none" && !hasList) {
    return <FirstRun />;
  }
  return <PlanBody failure={failure} finishedNow={finishedNow} onFailure={setFailure} plan={preview.data} />;
}
