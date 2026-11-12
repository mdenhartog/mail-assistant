import type { ReactElement } from "react";

import { retryAfterSecondsOf } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/Banner";

/** A new code may be asked for this many seconds after the last one; a longer wait is the hourly cap. */
const COOLDOWN_SECONDS = 60;
const SECONDS_PER_MINUTE = 60;

/** A 429 on the request for a code. */
interface RequestRefusal {
  kind: "cooldown" | "hourly";
  /** From `Retry-After`. */
  seconds: number;
}

/** Why the request for a code did not give a code. */
export type RequestFailure = RequestRefusal | { kind: "failed" };

/** How a code was refused, other than a plain wrong code. */
type DeadCode = "expired" | "exhausted";

function plural(count: number, unit: string): string {
  return `${String(count)} ${unit}${count === 1 ? "" : "s"}`;
}

/**
 * Sorts a failed request for a code: a 429 with a short `Retry-After` is the cooldown, a longer one
 * the hourly cap (a missing or unusable header counts as the normal cooldown); anything else just failed.
 */
export function requestFailureOf(error: unknown): RequestFailure {
  if (!(error instanceof ApiError) || error.status !== 429) {
    return { kind: "failed" };
  }
  const seconds = retryAfterSecondsOf(error) ?? COOLDOWN_SECONDS;
  return { kind: seconds > COOLDOWN_SECONDS ? "hourly" : "cooldown", seconds };
}

export interface RefusalBannerProps {
  refusal: RequestRefusal;
}

/**
 * The 429 banners: an info banner for the cooldown, an alert for the hourly cap (minutes rounded up).
 *
 * @example
 * <RefusalBanner refusal={{ kind: "cooldown", seconds: 41 }} />
 */
export function RefusalBanner({ refusal }: RefusalBannerProps): ReactElement {
  if (refusal.kind === "cooldown") {
    return (
      <Banner kind="info" title="Please wait before asking for another code.">
        {`You can try again in ${plural(refusal.seconds, "second")}.`}
      </Banner>
    );
  }
  const minutes = Math.ceil(refusal.seconds / SECONDS_PER_MINUTE);
  return (
    <Banner kind="danger" title="You have asked for too many codes this hour.">
      {`Try again in about ${plural(minutes, "minute")}.`}
    </Banner>
  );
}

export interface DeadCodeBannerProps {
  reason: DeadCode;
}

/**
 * The alert for a code that no longer works. Too many tries takes focus, because the field is disabled
 * and the button may still be counting down; after an expired code the button takes focus instead.
 *
 * @example
 * <DeadCodeBanner reason="expired" />
 */
export function DeadCodeBanner({ reason }: DeadCodeBannerProps): ReactElement {
  return reason === "expired" ? (
    <Banner kind="danger" title="This code has expired.">
      Send yourself a new one.
    </Banner>
  ) : (
    <Banner focusOnMount kind="danger" title="Too many wrong tries.">
      This code no longer works. Send a new code.
    </Banner>
  );
}
