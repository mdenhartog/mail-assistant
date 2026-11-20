import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { classifyPlanError } from "@/api/plan/plan.api";
import { planKey, useApprove, useDecide } from "@/api/plan/plan.queries";
import { MAX_IDS } from "@/api/plan/plan.types";
import type { Decision, DecisionScope, PlanFailure, PlanGroup, PlanView } from "@/api/plan/plan.types";
import type { SelectionUpdate } from "@/features/review/GroupPanel";
import { groupKey } from "@/features/review/text";

const EMPTY: ReadonlySet<number> = new Set<number>();

/** What went wrong and in which step, so the text can say whether a decision or the move failed. */
export interface ReviewFailure {
  step: "decision" | "approval";
  kind: PlanFailure["kind"];
}

export interface ReviewDecisions {
  selection: Readonly<Record<string, ReadonlySet<number>>>;
  selectedCount: number;
  failure: ReviewFailure | null;
  busy: boolean;
  onSelection: (key: string, update: SelectionUpdate) => void;
  decideGroup: (group: PlanGroup, decision: Decision) => void;
  decideSelected: (group: PlanGroup, decision: Decision, ids: number[]) => void;
  approve: () => Promise<boolean>;
  reload: () => void;
}

function scopesOf(group: PlanGroup, ids: number[] | null): DecisionScope[] {
  if (ids === null) {
    return [{ group: { from: group.from, to: group.to }, groupCount: group.count }];
  }
  const parts: DecisionScope[] = [];
  for (let start = 0; start < ids.length; start += MAX_IDS) {
    parts.push({ ids: ids.slice(start, start + MAX_IDS) });
  }
  return parts;
}

export function selectionOf(selection: Readonly<Record<string, ReadonlySet<number>>>, key: string): ReadonlySet<number> {
  return selection[key] ?? EMPTY;
}

function useSelection(): Pick<ReviewDecisions, "selection" | "selectedCount" | "onSelection"> & {
  clear: (key: string) => void;
} {
  const [selection, setSelection] = useState<Record<string, ReadonlySet<number>>>({});
  const onSelection = useCallback((key: string, update: SelectionUpdate) => {
    setSelection((current) => ({ ...current, [key]: update(current[key] ?? EMPTY) }));
  }, []);
  const clear = useCallback((key: string) => {
    setSelection((current) => ({ ...current, [key]: EMPTY }));
  }, []);
  const selectedCount = Object.values(selection).reduce((sum, ids) => sum + ids.size, 0);
  return { selection, selectedCount, onSelection, clear };
}

/**
 * What the ready plan lets the user do: select, record a decision for a group or for ticked mails, and approve.
 * Every request carries the plan id and the item count the user saw, so a plan that changed meanwhile is a 409 that
 * changes nothing (AC-13). Ticking only selects; a decision is recorded only by its own button.
 */
export function useReviewDecisions(plan: PlanView): ReviewDecisions {
  const queryClient = useQueryClient();
  const decide = useDecide();
  const approveMutation = useApprove();
  const { selection, selectedCount, onSelection, clear } = useSelection();
  const [failure, setFailure] = useState<ReviewFailure | null>(null);
  const planId = plan.id;

  const send = async (group: PlanGroup, decision: Decision, ids: number[] | null): Promise<void> => {
    if (planId === null) {
      return;
    }
    setFailure(null);
    try {
      for (const scope of scopesOf(group, ids)) {
        await decide.mutateAsync({ planId, itemCount: plan.counts.items, scope, decision });
      }
      clear(groupKey(group));
    } catch (error) {
      setFailure({ step: "decision", kind: classifyPlanError(error).kind });
    }
  };

  const approve = async (): Promise<boolean> => {
    if (planId === null) {
      return false;
    }
    setFailure(null);
    try {
      await approveMutation.mutateAsync({ planId, itemCount: plan.counts.items });
      return true;
    } catch (error) {
      setFailure({ step: "approval", kind: classifyPlanError(error).kind });
      return false;
    }
  };

  return {
    selection,
    selectedCount,
    failure,
    busy: decide.isPending || approveMutation.isPending,
    onSelection,
    decideGroup: (group, decision) => void send(group, decision, null),
    decideSelected: (group, decision, ids) => void send(group, decision, ids.length === group.count ? null : ids),
    approve,
    reload: () => {
      setFailure(null);
      void queryClient.invalidateQueries({ queryKey: planKey });
    },
  };
}
