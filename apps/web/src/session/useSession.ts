import type { UseQueryResult } from "@tanstack/react-query";

import type { components } from "@/api/schema";

export type SessionInfo = components["schemas"]["SessionInfo"];

export function useSession(): UseQueryResult<SessionInfo | null> {
  throw new Error("not implemented");
}
