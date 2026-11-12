import { useEffect, useRef } from "react";
import type { ReactElement, ReactNode } from "react";

import { Button } from "@/components/Button";

export type BannerKind = "danger" | "conflict" | "success" | "info";

export interface BannerProps {
  kind: BannerKind;
  title: string;
  children?: ReactNode;
  action?: { label: string; onClick: () => void };
  /** Only for blocking messages (a refusal, a conflict): moves focus to the banner on mount. */
  focusOnMount?: boolean;
}

interface Look {
  role: "alert" | "status";
  box: string;
  /** The circle takes the strong colour and the mark the soft one, never `currentColor`. */
  icon: string;
  mark: string;
}

const LOOKS: Record<BannerKind, Look> = {
  danger: { role: "alert", box: "border-danger bg-danger-soft text-danger", icon: "bg-danger text-danger-soft", mark: "!" },
  success: {
    role: "status",
    box: "border-success bg-success-soft text-success",
    icon: "bg-success text-success-soft",
    mark: "✓",
  },
  info: {
    role: "status",
    box: "border-primary bg-surface-raised text-text",
    icon: "bg-primary text-primary-contrast",
    mark: "i",
  },
  conflict: {
    role: "alert",
    box: "border-primary bg-surface-raised text-text",
    icon: "bg-primary text-primary-contrast",
    mark: "!",
  },
};

/**
 * Message box with a bold title, a mark that is not only colour, and an optional action.
 * The node is the live region: re-rendering with the same props keeps it, so it is announced once.
 *
 * @example
 * <Banner kind="danger" title="Could not save.">Nothing was changed.</Banner>
 */
export function Banner({ kind, title, children, action, focusOnMount = false }: BannerProps): ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const look = LOOKS[kind];
  useEffect(() => {
    if (focusOnMount) {
      ref.current?.focus();
    }
  }, [focusOnMount]);
  return (
    <div
      className={`flex items-start gap-3 rounded-control border-l-8 px-4 py-3 motion-safe:animate-rise ${look.box}`}
      ref={ref}
      role={look.role}
      tabIndex={focusOnMount ? -1 : undefined}
    >
      <span
        aria-hidden="true"
        className={`mt-0.5 inline-grid size-6 flex-none place-items-center rounded-full text-sm font-bold ${look.icon}`}
        data-banner-icon=""
      >
        {look.mark}
      </span>
      <div>
        <strong className="font-bold">{title}</strong>
        {children ? <> {children}</> : null}
        {action ? (
          <div className="mt-2">
            <Button onClick={action.onClick} variant="secondary">
              {action.label}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
