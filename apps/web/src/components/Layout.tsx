import type { ReactElement, ReactNode } from "react";

export interface LayoutAccount {
  maskedAddress: string;
  onSignOut: () => void;
  signingOut?: boolean;
  signOutFailed?: boolean;
}

export interface LayoutProps {
  account?: LayoutAccount;
  children: ReactNode;
}

export function Layout(props: LayoutProps): ReactElement {
  return <div>{props.children}</div>;
}
