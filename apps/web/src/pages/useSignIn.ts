import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { attemptsLeftOf, requestCode, verifyCode } from "@/api/auth";
import type { CodeFailure } from "@/pages/CodeStep";
import { paths } from "@/router/paths";
import { sessionKey } from "@/session/useSession";

export interface SignIn {
  /** The masked address once a code was sent; null while on step 1. */
  maskedAddress: string | null;
  sending: boolean;
  requestFailed: boolean;
  verifying: boolean;
  failure: CodeFailure | null;
  requestCode: (username: string) => void;
  verifyCode: (code: string) => void;
  useAnotherUsername: () => void;
}

/**
 * State of the two login steps. Nothing is stored: the username goes straight to the request,
 * the code stays in the field, and a right code ends in the settings whatever the URL says.
 *
 * @example
 * const signIn = useSignIn();
 */
export function useSignIn(): SignIn {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [maskedAddress, setMaskedAddress] = useState<string | null>(null);
  const [failure, setFailure] = useState<CodeFailure | null>(null);

  const request = useMutation({
    mutationFn: requestCode,
    onSuccess: (answer) => {
      setFailure(null);
      setMaskedAddress(answer.maskedAddress);
    },
  });
  const verify = useMutation({
    mutationFn: verifyCode,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: sessionKey });
      await navigate(paths.settings, { replace: true });
    },
    onError: (error) => {
      setFailure((previous) => ({ attemptsLeft: attemptsLeftOf(error), seq: (previous?.seq ?? 0) + 1 }));
    },
  });

  return {
    maskedAddress,
    sending: request.isPending,
    requestFailed: request.isError,
    verifying: verify.isPending,
    failure,
    requestCode: request.mutate,
    verifyCode: verify.mutate,
    useAnotherUsername: () => {
      request.reset();
      verify.reset();
      setFailure(null);
      setMaskedAddress(null);
    },
  };
}
