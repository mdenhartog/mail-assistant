import type { ButtonHTMLAttributes, ReactElement } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  loadingLabel?: string;
}

export function Button(props: ButtonProps): ReactElement {
  return <button type="button">{props.children}</button>;
}
