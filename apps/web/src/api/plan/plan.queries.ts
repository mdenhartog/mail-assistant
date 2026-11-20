import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseInfiniteQueryResult, UseMutationResult, UseQueryResult, InfiniteData } from "@tanstack/react-query";

import { approvePlan, fetchPlan, fetchPlanItems, moveBack, postDecision, searchPlanItems } from "@/api/plan/plan.api";
import { NO_FILTER, isFiltering } from "@/api/plan/plan.types";
import type {
  ApprovalResult,
  ApproveBody,
  DecisionBody,
  DecisionResult,
  GroupRef,
  ItemFilter,
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

/** The number of mails waiting for a decision, for the badge of the navigation; nothing while no ready plan is read. */
export function useOpenItems(enabled: boolean): number {
  const { data } = useQuery({
    queryKey: planKey,
    queryFn: fetchPlan,
    refetchOnWindowFocus: false,
    enabled,
    select: (plan) => (plan.state === "ready" ? plan.counts.pending : 0),
  });
  return data ?? 0;
}

/**
 * Pages of 100 items of one group (or of the whole plan with no group), fetched one by one with "Load more". With a
 * filter the pages come from the search route (a POST). The key holds the filter in memory only; it is never turned
 * into a URL, and no persister is set up, so the sender text is not stored.
 */
export function usePlanItems(
  group: GroupRef | null,
  enabled: boolean,
  filter: ItemFilter = NO_FILTER,
): UseInfiniteQueryResult<InfiniteData<PlanItemsPage, number>> {
  const searching = group !== null && isFiltering(filter);
  return useInfiniteQuery({
    queryKey: [...planKey, "items", group, searching ? filter : null],
    queryFn: ({ pageParam }) => (searching ? searchPlanItems(group, filter, pageParam) : fetchPlanItems(group, pageParam)),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasMore ? last.page + 1 : undefined),
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
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
