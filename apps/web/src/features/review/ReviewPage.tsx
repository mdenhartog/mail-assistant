import type { ReactElement } from "react";

import { useCategories } from "@/api/categories/categories.queries";
import { usePlan } from "@/api/plan/plan.queries";
import type { PlanView } from "@/api/plan/plan.types";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/Banner";
import { AppliedPanel } from "@/features/review/AppliedPanel";
import { clockText } from "@/features/review/copy";
import { Building, NoPlan, Notice } from "@/features/review/PlanStates";
import { ReadyReview } from "@/features/review/ReadyReview";
import { usePageTitle } from "@/pages/usePageTitle";

function Loading(): ReactElement {
  return (
    <div aria-busy="true" className="mt-6">
      <p className="text-text-muted" role="status">
        Loading your review
      </p>
      <div aria-hidden="true" className="mt-4 grid gap-4">
        {[0, 1, 2].map((row) => (
          <div className="h-24 rounded-card bg-divider motion-safe:animate-pulse" data-skeleton="" key={row} />
        ))}
      </div>
    </div>
  );
}

function LoadFailed({ error, onRetry }: { error: unknown; onRetry: () => void }): ReactElement {
  const tooMany = error instanceof ApiError && error.status === 429;
  return (
    <div className="mt-6">
      <Banner
        action={{ label: "Try again", onClick: onRetry }}
        kind="danger"
        title={tooMany ? "Too many requests." : "Could not load your review."}
      >
        {tooMany ? "Wait a minute and try again." : "Check your connection and try again."}
      </Banner>
    </div>
  );
}

/** The plan Move back is for: the open plan once applied, or the last applied one when none is open. */
function appliedPlan(plan: PlanView): { id: string; at: string | null } | null {
  if (plan.state === "applied" && plan.id !== null) {
    return { id: plan.id, at: clockText(plan.lastPlan?.appliedAt ?? null) };
  }
  return plan.state === null && plan.lastPlan ? { id: plan.lastPlan.id, at: clockText(plan.lastPlan.appliedAt) } : null;
}

function Content({ plan }: { plan: PlanView }): ReactElement {
  const categories = useCategories();
  const applied = appliedPlan(plan);
  if (applied) {
    return <AppliedPanel at={applied.at} planId={applied.id} />;
  }
  if (plan.state === null) {
    return <NoPlan />;
  }
  if (plan.state === "building") {
    return <Building plan={plan} />;
  }
  if (plan.state !== "ready") {
    return <Notice plan={plan} state={plan.state} />;
  }
  if (categories.isError) {
    return <LoadFailed error={categories.error} onRetry={() => void categories.refetch()} />;
  }
  if (categories.isPending) {
    return <Loading />;
  }
  return <ReadyReview categories={categories.data.categories} key={plan.id} plan={plan} />;
}

/** `/review`: the plan of moves for older mail, from building to applied (the states of the brief). */
export function ReviewPage(): ReactElement {
  usePageTitle("Review moves");
  const { data, isPending, isError, error, refetch } = usePlan();
  let content: ReactElement;
  if (isPending) {
    content = <Loading />;
  } else if (isError) {
    content = (
      <LoadFailed
        error={error}
        onRetry={() => {
          void refetch();
        }}
      />
    );
  } else {
    content = <Content plan={data} />;
  }
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-text wrap-anywhere">Review moves</h1>
      {content}
    </div>
  );
}
