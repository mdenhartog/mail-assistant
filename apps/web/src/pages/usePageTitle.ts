import { useEffect } from "react";

/** Sets the document title to "<screen> - Mail Assistant". */
export function usePageTitle(screen: string): void {
  useEffect(() => {
    document.title = `${screen} - Mail Assistant`;
  }, [screen]);
}
