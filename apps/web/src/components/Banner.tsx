import type { ReactElement, ReactNode } from "react";

export type BannerKind = "danger" | "conflict" | "success" | "info";

export interface BannerProps {
  kind: BannerKind;
  title: string;
  children?: ReactNode;
  action?: { label: string; onClick: () => void };
  focusOnMount?: boolean;
}

export function Banner(props: BannerProps): ReactElement {
  return <div>{props.title}</div>;
}
