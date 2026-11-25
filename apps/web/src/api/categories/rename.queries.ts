import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { fetchDeletedLabels, fetchRenamePreview, postRenameConfirmation, postRenameRestore } from "@/api/categories/rename.api";
import type { DeletedLabels, RenameConfirmation, RenamePreview } from "@/api/categories/rename.types";

const previewKey = ["label-rename"] as const;
const deletedKey = ["label-rename", "deleted"] as const;

/** While the agent renames, the preview is read again at this interval. */
export const RENAME_POLL_MS = 5000;

/** The rename plan and its state; read again every few seconds while the agent is renaming. */
export function useRenamePreview(): UseQueryResult<RenamePreview> {
  return useQuery({
    queryKey: previewKey,
    queryFn: fetchRenamePreview,
    refetchInterval: (query) => (query.state.data?.state === "confirmed" ? RENAME_POLL_MS : false),
  });
}

/** The recently deleted labels with the retention period. */
export function useDeletedLabels(): UseQueryResult<DeletedLabels> {
  return useQuery({ queryKey: deletedKey, queryFn: fetchDeletedLabels });
}

/** Sends the confirmation once; the plan is read again either way, so a changed plan shows up. */
export function useConfirmRename(): UseMutationResult<string, Error, RenameConfirmation> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postRenameConfirmation,
    onSettled: () => queryClient.invalidateQueries({ queryKey: previewKey }),
  });
}

/** Asks for the old names back; the plan is read again afterwards. */
export function useRestoreRename(): UseMutationResult<string, Error, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postRenameRestore,
    onSettled: () => queryClient.invalidateQueries({ queryKey: previewKey }),
  });
}
