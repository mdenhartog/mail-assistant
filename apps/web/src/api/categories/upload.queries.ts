import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult } from "@tanstack/react-query";

import { confirmUpload, fetchExport, restorePrevious, uploadFile } from "@/api/categories/upload.api";
import type { CategoryList } from "@/api/categories/categories.types";
import type { UploadPreview } from "@/api/categories/upload.types";

const categoriesKey = ["categories"] as const;

/** Checks a file; the answer is a preview and nothing is stored. */
export function useUploadFile(): UseMutationResult<UploadPreview, Error, File> {
  return useMutation({ mutationFn: uploadFile });
}

/** Replaces the whole list with the previewed file; the new list becomes the stored copy. */
export function useConfirmUpload(): UseMutationResult<CategoryList, Error, { previewId: string; fileHash: string }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: confirmUpload,
    onSuccess: (saved) => {
      queryClient.setQueryData(categoriesKey, saved);
    },
  });
}

/** Stores a new version equal to the one before the current one. */
export function useRestorePrevious(): UseMutationResult<CategoryList, Error, number> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: restorePrevious,
    onSuccess: (saved) => {
      queryClient.setQueryData(categoriesKey, saved);
    },
  });
}

/** The exported list as text, for the copy option. */
export function useExportText(): UseMutationResult<string, Error, void> {
  return useMutation({ mutationFn: fetchExport });
}
