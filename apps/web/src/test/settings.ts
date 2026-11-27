/** The label cleanup values and ranges the api sends next to the times, for the Settings tests. */
export const CLEANUP = { waitingMinutes: 720, protectionDays: 7, retentionDays: 30 } as const;

export const RANGES = {
  waitingMinutes: { min: 5, max: 720, default: 720 },
  protectionDays: { min: 1, max: 30, default: 7 },
  retentionDays: { min: 7, max: 90, default: 30 },
} as const;
