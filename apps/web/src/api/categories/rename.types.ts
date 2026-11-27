import type { components } from "@/api/schema";

export type RenamePreview = components["schemas"]["RenamePreview"];
export type RenameItem = components["schemas"]["RenameItem"];
export type DeletedLabels = components["schemas"]["DeletedLabels"];

/** What the user typed and chose: the hash of the plan that was shown and the ids that stay as they are. */
export interface RenameConfirmation {
  planHash: string;
  skippedIds: string[];
}

/** What a failed confirm or restore means for the page. */
export type RenameFailure = "changed" | "unknown-skip" | "nothing-to-restore" | "session" | "failed";
