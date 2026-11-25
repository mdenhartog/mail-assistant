/** The texts of the rename section. Label names never go through here: they are rendered as plain text where they belong. */

export function labels(count: number): string {
  return `${String(count)} ${count === 1 ? "label" : "labels"}`;
}

export function mails(count: number): string {
  return `${String(count)} ${count === 1 ? "mail" : "mails"}`;
}

export const RENAME = {
  title: "Rename your labels",
  loading: "Loading the rename preview",
  loadFailed: "Could not load the rename preview.",
  checkConnection: "Check your connection and try again.",
  tryAgain: "Try again",
  empty: "Load your YAML file first: the list is no longer read from Gmail.",
  emptyHelp: "Use Import and export below to upload it. The assistant only uses the labels from your list.",
  intro: "These labels still start with the old Assistant prefix. Renaming removes that prefix. Mail stays on every label and nothing is renamed until you confirm.",
  summary: (labelCount: number, mailCount: number): string => `${labels(labelCount)}, ${mails(mailCount)}`,
  sort: "Sort by mail count",
  mostFirst: "Most mails first",
  fewestFirst: "Fewest mails first",
  now: "Now",
  becomes: "Becomes",
  merge: (count: number): string => `Merge ${mails(count)} into an existing label`,
  skip: "Skip",
  skipped: "Skipped: keeps its name.",
  start: "Rename these labels",
  starting: "Sending...",
  startHelp: "You confirm once more before anything changes.",
  allSkipped: "Every label is skipped, so there is nothing to rename.",
  dialogTitle: (count: number): string => `Rename ${labels(count)}?`,
  dialogBody: (count: number, skippedCount: number): string =>
    `This renames ${labels(count)} in Gmail${skippedCount > 0 ? `; ${labels(skippedCount)} you skipped keep their names` : ""}. Mail stays where it is, and you can restore the old names afterwards.`,
  dialogField: (count: number): string => `Type ${String(count)} or RENAME to confirm`,
  dialogHint: "This is a safety step, so a stray click cannot start the rename.",
  dialogMismatch: (count: number): string => `That does not match. Type ${String(count)} or RENAME.`,
  confirm: "Rename labels",
  cancel: "Cancel",
  changed: "The plan changed.",
  changedBody: "Nothing was renamed. The list below is the new plan; check it and confirm again.",
  unknownSkip: "A label you skipped is no longer in the plan.",
  unknownSkipBody: "Nothing was renamed. The list below is up to date; check it and confirm again.",
  startFailed: "Could not start the rename.",
  startFailedBody: "Nothing was renamed. Check your connection and try again.",
  sessionEnded: "Your session ended.",
  sessionEndedBody: "Your choices are kept. Sign in again, then come back to this page.",
  signIn: "Sign in again",
  inProgress: "Renaming is in progress",
  inProgressBody: "This page updates by itself. Telegram tells you when it is done.",
} as const;

export const RESULT = {
  title: "Renaming finished",
  notice: "Gmail apps may show the old names for a while.",
  summary: (renamed: number, total: number, skipped: number, kept: number): string =>
    `${String(renamed)} of ${labels(total)} renamed${skipped > 0 ? `, ${String(skipped)} skipped` : ""}${kept > 0 ? `, ${String(kept)} kept` : ""}`,
  renamed: (oldName: string, newName: string): string => `${oldName} is now ${newName}`,
  merged: (oldName: string, newName: string): string => `${oldName} was merged into ${newName}`,
  skipped: (oldName: string): string => `${oldName} was skipped and keeps its name`,
  kept: (oldName: string): string => `${oldName} was kept because it changed in the meantime`,
  restore: "Restore the old names",
  restoreSending: "Sending...",
  restoreHelp: "The agent gives every renamed label its old name again. Mail stays where it is.",
  dialogTitle: "Restore the old names?",
  dialogBody: "The renamed labels get the names they had before. Mail stays where it is.",
  dialogConfirm: "Restore names",
  dialogCancel: "Keep the new names",
  requested: "The old names are being restored.",
  requestedBody: "Telegram tells you when it is done. Gmail apps may show the new names for a while.",
  nothing: "Nothing to restore.",
  nothingBody: "The rename is not finished or was restored already.",
  failed: "Could not start the restore.",
  failedBody: "Nothing was changed. Check your connection and try again.",
} as const;

export const DELETED = {
  title: "Recently deleted labels",
  loading: "Loading the recently deleted labels",
  loadFailed: "Could not load the recently deleted labels.",
  intro: (days: number): string =>
    `Labels the assistant deleted are listed here for ${String(days)} days. This list is read-only; to get a label back, create it again in Gmail.`,
  empty: (days: number): string => `No label was deleted in the last ${String(days)} days.`,
  deletedOn: "Deleted on",
} as const;
