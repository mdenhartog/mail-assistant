import type { CodeFailure } from "@/pages/CodeStep";

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

/** State of the two login steps. */
export function useSignIn(): SignIn {
  return {
    maskedAddress: null,
    sending: false,
    requestFailed: false,
    verifying: false,
    failure: null,
    requestCode: () => undefined,
    verifyCode: () => undefined,
    useAnotherUsername: () => undefined,
  };
}
