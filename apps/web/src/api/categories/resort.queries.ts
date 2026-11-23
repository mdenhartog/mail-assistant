import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { fetchLatestThreshold, postResort } from "@/api/categories/resort.api";
import type { ResortLatest, ResortRequested } from "@/api/categories/resort.types";
import { planKey } from "@/api/plan/plan.queries";

const latestKey = ["resort-requests", "latest"] as const;

/** The value the threshold field starts with. Kept until a request changes it: a refetch would replace what the user types. */
export function useLatestThreshold(): UseQueryResult<ResortLatest> {
  return useQuery({
    queryKey: latestKey,
    queryFn: fetchLatestThreshold,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** Sends one request; the stored threshold becomes the field's value and the open plan is read again. */
export function useRequestResort(): UseMutationResult<ResortRequested, Error, number> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postResort,
    onSuccess: (stored) => {
      queryClient.setQueryData<ResortLatest>(latestKey, { threshold: stored.threshold });
      void queryClient.invalidateQueries({ queryKey: planKey });
    },
  });
}
