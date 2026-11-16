import type { ReactElement } from "react";
import { Link } from "react-router";

import type { PlanState, PlanView } from "@/api/plan/plan.types";
import { Banner } from "@/components/Banner";
import { Card } from "@/components/Card";
import { Progress } from "@/components/Progress";
import { clockText, onDayAtText } from "@/features/review/copy";
import { paths } from "@/router/paths";

function EditCategories(): ReactElement {
  return (
    <p className="mt-3">
      <Link
        className="inline-flex min-h-11 items-center font-semibold text-primary underline"
        to={paths.categories}
      >
        Edit your categories
      </Link>
    </p>
  );
}

/** No review at all: what makes one appear. */
export function NoPlan(): ReactElement {
  return (
    <div className="mt-6">
      <Banner kind="info" title="No review is open.">
        A review appears here when you change a description or delete a
        category. Until then your mail is sorted into your categories as it
        arrives.
      </Banner>
      <EditCategories />
    </div>
  );
}

/** The agent is still listing mail: how far it is, and that nothing moves while it does. */
export function Building({ plan }: { plan: PlanView }): ReactElement {
  const { checked, estimate } = plan.progress;
  const total = estimate === null ? null : Math.max(estimate, checked);
  return (
    <div aria-busy="true" className="mt-6">
      <Card>
        <p className="text-text">
          {total === null
            ? `${String(checked)} checked so far, nothing moves yet.`
            : `${String(checked)} of about ${String(total)} checked, nothing moves yet.`}
        </p>
        {total === null ? null : (
          <div className="mt-3">
            <Progress label="Mails checked" max={total} value={checked} />
          </div>
        )}
        <p className="mt-3 text-text-muted">
          The review is being prepared. You can leave this page and come back.
        </p>
      </Card>
    </div>
  );
}

type Notice = { kind: "info"; title: string; body: string; link?: true };

function noticeFor(
  state: PlanState,
  plan: PlanView,
  endedAt: string | null,
): Notice {
  switch (state) {
    case "scheduled": {
      const at = clockText(plan.applyAfter);
      return {
        kind: "info",
        title:
          at === null
            ? "Your mails are about to move."
            : `Your mails move at ${at}.`,
        body: "Only labels change. To stop this, use Cancel in the Telegram message.",
      };
    }
    case "applying":
      return {
        kind: "info",
        title: "Your mails are being moved.",
        body: "Only labels change. This page updates by itself.",
      };
    case "replaced":
      return {
        kind: "info",
        title: `This review was replaced${onDayAtText(endedAt)}.`,
        body: "You changed your categories, so a new review is being prepared. Nothing from this one was moved.",
        link: true,
      };
    case "cancelled":
      return {
        kind: "info",
        title: `This review was cancelled${onDayAtText(endedAt)}.`,
        body: "Nothing was moved.",
        link: true,
      };
    default:
      return {
        kind: "info",
        title: "This review was too old.",
        body: "Nothing was moved. A new review is made when your categories change.",
      };
  }
}

/** The states that only report: scheduled, applying, replaced, cancelled and discarded. */
export function Notice({
  state,
  plan,
  endedAt = null,
}: {
  state: PlanState;
  plan: PlanView;
  /** When the plan ended (ISO time), for a plan that is no longer open; shown as "on 15 Nov at 14:20". */
  endedAt?: string | null;
}): ReactElement {
  const notice = noticeFor(state, plan, endedAt);
  return (
    <div className="mt-6">
      <Banner kind={notice.kind} title={notice.title}>
        {notice.body}
      </Banner>
      {notice.link ? <EditCategories /> : null}
    </div>
  );
}
