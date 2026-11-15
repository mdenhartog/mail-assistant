import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseInfiniteQueryResult, UseMutationResult, UseQueryResult, InfiniteData } from "@tanstack/react-query";

import { approvePlan, fetchPlan, fetchPlanItems, moveBack, postDecision } from "@/api/plan/plan.api";
import type {
  ApprovalResult,
  ApproveBody,
  DecisionBody,
  DecisionResult,
  GroupRef,
  MoveBackResult,
  PlanItemsPage,
  PlanView,
} from "@/api/plan/plan.types";

export const planKey = ["plan"] as const;

/** States in which the agent is still working, so the page asks again by itself. */
const MOVING = new Set(["building", "scheduled", "applying"]);
const POLL_MS = 5000;

/** The open plan. While the agent builds or applies it, the page refreshes every few seconds. */
export function usePlan(): UseQueryResult<PlanView> {
  return useQuery({
    queryKey: planKey,
    queryFn: fetchPlan,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state !== null && state !== undefined && MOVING.has(state) ? POLL_MS : false;
    },
  });
}

/** Pages of 100 items of one group (or of the whole plan with no group), fetched one by one with "Load more". */
export function usePlanItems(
  group: GroupRef | null,
  enabled: boolean,
): UseInfiniteQueryResult<InfiniteData<PlanItemsPage, number>> {
  return useInfiniteQuery({
    queryKey: [...planKey, "items", group],
    queryFn: ({ pageParam }) => fetchPlanItems(group, pageParam),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasMore ? last.page + 1 : undefined),
    refetchOnWindowFocus: false,
    enabled,
  });
}

/** Records a decision; the plan and every opened group are read again so the rows keep their place but show the new decision. */
export function useDecide(): UseMutationResult<DecisionResult, Error, DecisionBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postDecision,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: planKey }),
    onError: () => queryClient.invalidateQueries({ queryKey: planKey }),
  });
}

export function useApprove(): UseMutationResult<ApprovalResult, Error, ApproveBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: approvePlan,
    onSettled: () => queryClient.invalidateQueries({ queryKey: planKey }),
  });
}

export function useMoveBack(): UseMutationResult<MoveBackResult, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: moveBack,
    onSettled: () => queryClient.invalidateQueries({ queryKey: planKey }),
  });
}
