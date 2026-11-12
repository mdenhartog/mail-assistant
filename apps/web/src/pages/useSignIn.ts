import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { attemptsLeftOf, verifyCode } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { CodeFailure } from "@/pages/CodeStep";
import { useClock } from "@/pages/clock";
import type { RequestFailure } from "@/pages/refusals";
import { useCodeSending } from "@/pages/useCodeSending";
import type { ResendState } from "@/pages/useCodeSending";
import { paths } from "@/router/paths";
import { sessionKey } from "@/session/useSession";

/** A code is valid for ten minutes (ADR-0036). */
const CODE_LIFETIME_MS = 10 * 60 * 1000;

export interface SignIn {
  /** The masked address once a code was sent; null while on step 1. */
  maskedAddress: string | null;
  sending: boolean;
  requestFailure: RequestFailure | null;
  verifying: boolean;
  failure: CodeFailure | null;
  /** Changes when the code field must start empty again. */
  codeKey: number;
  resend: ResendState;
  requestCode: (username: string) => void;
  verifyCode: (code: string) => void;
  useAnotherUsername: () => void;
}

/**
 * Sorts a refused code. A 400 after the code's ten minutes is an expired code; no tries left, or a 429
 * on the code, is a dead one; anything else is a plain wrong code. A locked web answers like any wrong
 * code, so nothing here can tell it apart (W-1).
 */
function failureOf(error: unknown, expired: boolean, seq: number): CodeFailure {
  const attemptsLeft = attemptsLeftOf(error);
  const dead = attemptsLeft === 0 || (error instanceof ApiError && error.status === 429);
  const kind = expired ? "expired" : dead ? "exhausted" : "wrong";
  return { kind, attemptsLeft, seq };
}

/**
 * State of the two login steps. The code stays in the field, and a right code ends in the settings
 * whatever the URL says.
 *
 * @example
 * const signIn = useSignIn();
 */
export function useSignIn(): SignIn {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const clock = useClock();
  const [failure, setFailure] = useState<CodeFailure | null>(null);
  const [codeKey, setCodeKey] = useState(0);
  const sending = useCodeSending(() => {
    setFailure(null);
    setCodeKey((key) => key + 1);
  });

  const verify = useMutation({
    mutationFn: verifyCode,
    onMutate: sending.dismissSent,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: sessionKey });
      await navigate(paths.settings, { replace: true });
    },
    onError: (error) => {
      const expired = error instanceof ApiError && error.status === 400 && clock.now() - sending.sentAt() > CODE_LIFETIME_MS;
      const next = failureOf(error, expired, (failure?.seq ?? 0) + 1);
      setFailure(next);
      if (next.kind !== "wrong") {
        setCodeKey((key) => key + 1);
      }
    },
  });

  return {
    maskedAddress: sending.maskedAddress,
    sending: sending.sending,
    requestFailure: sending.requestFailure,
    verifying: verify.isPending,
    failure,
    codeKey,
    resend: sending.resend,
    requestCode: sending.requestCode,
    verifyCode: verify.mutate,
    useAnotherUsername: () => {
      sending.reset();
      verify.reset();
      setFailure(null);
    },
  };
}
