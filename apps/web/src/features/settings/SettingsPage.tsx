import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";
import { SettingsForm } from "@/features/settings/SettingsForm";
import { useSettings } from "@/features/settings/useSettings";
import { usePageTitle } from "@/pages/usePageTitle";

function Loading(): ReactElement {
  return (
    <div aria-busy="true" className="mt-6">
      <p className="text-text-muted">Loading your settings</p>
      <div aria-hidden="true" className="mt-4 grid gap-4 sm:grid-cols-2">
        {[0, 1, 2, 3].map((row) => (
          <div className="h-28 rounded-card bg-divider motion-safe:animate-pulse" data-skeleton="" key={row} />
        ))}
      </div>
    </div>
  );
}

/** `/settings`: loads the stored settings, then shows the form. */
export function SettingsPage(): ReactElement {
  usePageTitle("Settings");
  const { data, isPending, isError, refetch } = useSettings();
  let content: ReactElement;
  if (isPending) {
    content = <Loading />;
  } else if (isError) {
    content = (
      <div className="mt-6">
        <Banner
          action={{
            label: "Try again",
            onClick: () => {
              void refetch();
            },
          }}
          kind="danger"
          title="Could not load your settings."
        >
          Check your connection and try again.
        </Banner>
      </div>
    );
  } else {
    content = <SettingsForm settings={data} />;
  }
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-text">Settings</h1>
      {content}
    </div>
  );
}
