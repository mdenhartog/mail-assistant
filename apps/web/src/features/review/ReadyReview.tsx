import { useState } from "react";
import type { ReactElement } from "react";

import type { CategoryItem } from "@/api/categories/categories.types";
import type { PlanView } from "@/api/plan/plan.types";
import { Banner } from "@/components/Banner";
import { ActionBar } from "@/features/review/ActionBar";
import { ApproveDialog } from "@/features/review/ApproveDialog";
import { ReviewGroup } from "@/features/review/ReviewGroup";
import { SelectionLive } from "@/features/review/SelectionLive";
import { groupKey, groupTitle } from "@/features/review/text";
import { selectionOf, useReviewDecisions } from "@/features/review/useReviewDecisions";
import type { ReviewFailure } from "@/features/review/useReviewDecisions";

function FailureBanner({ failure, onReload }: { failure: ReviewFailure; onReload: () => void }): ReactElement {
  if (failure.kind === "conflict") {
    return (
      <Banner action={{ label: "Reload the review", onClick: onReload }} focusOnMount kind="conflict" title="The review changed.">
        Nothing was changed. Reload it to see what is there now.
      </Banner>
    );
  }
  if (failure.kind === "rate-limited") {
    return (
      <Banner kind="danger" title="Too many requests.">
        Wait a minute and try again.
      </Banner>
    );
  }
  return failure.step === "approval" ? (
    <Banner kind="danger" title="Could not move your mails. Nothing was changed.">
      Try again.
    </Banner>
  ) : (
    <Banner kind="danger" title="Could not save your decision.">
      Nothing was changed. Try again.
    </Banner>
  );
}

function Notes({ plan }: { plan: PlanView }): ReactElement {
  const { checked, cap, unclear } = plan.progress;
  return (
    <>
      {cap > 0 && checked >= cap ? (
        <div className="mt-4">
          <Banner kind="info" title="Older mail was not looked at.">
            {`This review covers the newest ${String(cap)} mails. The rest stays where it is.`}
          </Banner>
        </div>
      ) : null}
      {unclear > 0 ? (
        <p className="mt-4 text-text">
          {`${String(unclear)} ${unclear === 1 ? "mail with two Assistant labels is" : "mails with two Assistant labels are"} left out, because it is not clear where ${unclear === 1 ? "it belongs" : "they belong"}.`}
        </p>
      ) : null}
    </>
  );
}

export interface ReadyReviewProps {
  plan: PlanView;
  categories: readonly CategoryItem[];
}

/**
 * A plan that is ready: the groups collapsed with their decisions, the live region for the selection count, the
 * sticky bar and the summary dialog. Approving does not happen anywhere but the dialog.
 */
export function ReadyReview({ plan, categories }: ReadyReviewProps): ReactElement {
  const decisions = useReviewDecisions(plan);
  const [asking, setAsking] = useState(false);
  const { approved, pending } = plan.counts;
  return (
    <section>
      <p className="mt-4 text-text">
        These mails would be filed differently with your categories. Nothing moves until you approve it, and only labels
        change.
      </p>
      <Notes plan={plan} />
      {decisions.failure ? (
        <div className="mt-4">
          <FailureBanner failure={decisions.failure} onReload={decisions.reload} />
        </div>
      ) : null}
      <h2 className="mt-6 font-display text-xl text-text">Mails that would move</h2>
      <ul className="mt-3 flex flex-col gap-4">
        {plan.groups.map((group) => (
          <ReviewGroup
            busy={decisions.busy}
            group={group}
            key={groupKey(group)}
            onDecideGroup={decisions.decideGroup}
            onDecideSelected={decisions.decideSelected}
            onSelection={decisions.onSelection}
            selected={selectionOf(decisions.selection, groupKey(group))}
            title={groupTitle(group, categories)}
          />
        ))}
      </ul>
      <SelectionLive count={decisions.selectedCount} />
      <ActionBar approved={approved} onMove={() => { setAsking(true); }} undecided={pending} />
      <ApproveDialog
        categories={categories}
        onCancel={() => { setAsking(false); }}
        onConfirm={() => {
          void decisions.approve().then(() => {
            setAsking(false);
          });
        }}
        open={asking}
        plan={plan}
        tally={decisions.tally}
      />
    </section>
  );
}
