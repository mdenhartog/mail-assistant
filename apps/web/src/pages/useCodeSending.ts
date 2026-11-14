import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { requestCode } from "@/api/auth";
import type { RequestCodeAnswer } from "@/api/auth";
import { useClock } from "@/pages/clock";
import { requestFailureOf } from "@/pages/refusals";
import type { RequestFailure } from "@/pages/refusals";

/** What the resend control shows above the field. */
export type ResendNotice = { kind: "sent" } | RequestFailure;

/** Everything the code step needs to offer "Send a new code". */
export interface ResendState {
  sending: boolean;
  /** Epoch milliseconds before which no new code may be asked for; null when none is pending. */
  deadline: number | null;
  /** The wait comes from the hourly cap, so it is explained in minutes, not counted in seconds. */
  hourly: boolean;
  notice: ResendNotice | null;
  onResend: () => void;
}

export interface CodeSending {
  /** The masked address once a code was sent; null while on step 1. */
  maskedAddress: string | null;
  sending: boolean;
  requestFailure: RequestFailure | null;
  resend: ResendState;
  /** Epoch milliseconds when the live code was sent. */
  sentAt: () => number;
  requestCode: (username: string) => void;
  /** Drops the "new code was sent" notice. */
  dismissSent: () => void;
  reset: () => void;
}

interface Cooldown {
  until: number | null;
  hourly: boolean;
  notice: ResendNotice | null;
}

const NO_COOLDOWN: Cooldown = { until: null, hourly: false, notice: null };

function afterSend(now: number, answer: RequestCodeAnswer, notice: ResendNotice | null): Cooldown {
  return { until: now + answer.resendAfterSeconds * 1000, hourly: false, notice };
}

function afterFailure(now: number, failure: RequestFailure, previous: Cooldown): Cooldown {
  if (failure.kind === "failed") {
    return { ...previous, notice: failure };
  }
  return { until: now + failure.seconds * 1000, hourly: failure.kind === "hourly", notice: failure };
}

/**
 * Asking for a code and asking again. The username stays in memory only, for the resend; the wait
 * before the next code comes from the answer (60 seconds) or from `Retry-After` on a 429.
 *
 * @example
 * const sending = useCodeSending(() => setFailure(null));
 */
export function useCodeSending(onNewCode: () => void): CodeSending {
  const clock = useClock();
  const username = useRef("");
  const sentAt = useRef(0);
  const [maskedAddress, setMaskedAddress] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState<Cooldown>(NO_COOLDOWN);

  const sent = (answer: RequestCodeAnswer, notice: ResendNotice | null): void => {
    const now = clock.now();
    sentAt.current = now;
    setMaskedAddress(answer.maskedAddress);
    setCooldown(afterSend(now, answer, notice));
  };
  const request = useMutation({ mutationFn: requestCode, onSuccess: (answer) => { sent(answer, null); } });
  const again = useMutation({
    mutationFn: () => requestCode(username.current),
    onMutate: () => {
      setCooldown((previous) => ({ ...previous, notice: null }));
    },
    onSuccess: (answer) => {
      sent(answer, { kind: "sent" });
      onNewCode();
    },
    onError: (error) => {
      const now = clock.now();
      setCooldown((previous) => afterFailure(now, requestFailureOf(error), previous));
    },
  });

  return {
    maskedAddress,
    sending: request.isPending,
    requestFailure: request.isError ? requestFailureOf(request.error) : null,
    resend: { sending: again.isPending, deadline: cooldown.until, hourly: cooldown.hourly, notice: cooldown.notice, onResend: again.mutate },
    sentAt: () => sentAt.current,
    requestCode: (name) => {
      username.current = name;
      request.mutate(name);
    },
    dismissSent: () => {
      setCooldown((previous) => (previous.notice?.kind === "sent" ? { ...previous, notice: null } : previous));
    },
    reset: () => {
      request.reset();
      again.reset();
      username.current = "";
      setMaskedAddress(null);
      setCooldown(NO_COOLDOWN);
    },
  };
}
