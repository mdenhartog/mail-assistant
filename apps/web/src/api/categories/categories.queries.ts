import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { classifySaveError, fetchCategories, putCategories } from "@/api/categories/categories.api";
import type { CategoryList, CategoryListUpdate } from "@/api/categories/categories.types";

const categoriesKey = ["categories"] as const;

/**
 * The stored list. Kept until a save changes it: a refetch while the user types would replace the form
 * under their hands.
 */
export function useCategories(): UseQueryResult<CategoryList> {
  return useQuery({
    queryKey: categoriesKey,
    queryFn: fetchCategories,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** Saves the whole list on the version it was based on; the answer, or the 409's current list, becomes the stored copy. */
export function useSaveCategories(): UseMutationResult<CategoryList, Error, CategoryListUpdate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: putCategories,
    onSuccess: (saved) => {
      queryClient.setQueryData(categoriesKey, saved);
    },
    onError: (error) => {
      const outcome = classifySaveError(error);
      if (outcome.kind === "conflict") {
        queryClient.setQueryData(categoriesKey, outcome.current);
      }
    },
  });
}
