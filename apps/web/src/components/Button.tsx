import type { ButtonHTMLAttributes, MouseEvent, ReactElement } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  /** While true the label is replaced, the button stays focusable and ignores clicks. */
  loading?: boolean;
  loadingLabel?: string;
}

const BASE =
  "inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-pill border-2 border-transparent " +
  "font-semibold text-center motion-safe:transition-transform motion-safe:duration-200 motion-safe:ease-spring " +
  "motion-safe:active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 aria-disabled:cursor-not-allowed " +
  "aria-disabled:opacity-60";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary px-6 text-primary-contrast",
  secondary: "border-border bg-surface-raised px-5 text-text",
  ghost: "px-3 text-text",
  danger: "bg-danger px-6 text-surface-raised",
};

function flag(on: boolean): true | undefined {
  return on ? true : undefined;
}

function classNames(...names: (string | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

/**
 * Pill button. `loading` (for example while saving) swaps the label and sets `aria-disabled`
 * instead of `disabled`, so focus stays on the button and a second click does nothing.
 *
 * @example
 * <Button loading={saving} onClick={save} variant="primary">Save changes</Button>
 */
export function Button({
  variant = "secondary",
  loading,
  loadingLabel = "Saving...",
  children,
  className,
  disabled,
  onClick,
  type = "button",
  ...rest
}: ButtonProps): ReactElement {
  const busy = loading === true;
  const handleClick = (event: MouseEvent<HTMLButtonElement>): void => {
    if (busy) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };
  return (
    <button
      {...rest}
      aria-busy={flag(busy)}
      aria-disabled={flag(busy || disabled === true)}
      className={classNames(BASE, VARIANTS[variant], className)}
      disabled={disabled}
      onClick={handleClick}
      type={type}
    >
      {busy ? loadingLabel : children}
    </button>
  );
}
