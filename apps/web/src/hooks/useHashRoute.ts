import { startTransition, useEffect, useState } from "react";

export type AppView =
  | "overview"
  | "chapters"
  | "assets"
  | "workflow"
  | "evolution"
  | "monitoring"
  | "preview"
  | "settings";

const DEFAULT_VIEW: AppView = "overview";
const SUPPORTED_VIEWS = new Set<AppView>([
  "overview",
  "chapters",
  "assets",
  "workflow",
  "evolution",
  "monitoring",
  "preview",
  "settings",
]);

function readHash(): AppView {
  const rawHash = window.location.hash.replace(/^#/, "") as AppView;
  if (SUPPORTED_VIEWS.has(rawHash)) {
    return rawHash;
  }
  return DEFAULT_VIEW;
}

export function useHashRoute() {
  const [view, setView] = useState<AppView>(() => readHash());

  useEffect(() => {
    const handleHashChange = () => {
      setView(readHash());
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  const navigate = (nextView: AppView) => {
    startTransition(() => {
      window.location.hash = nextView;
      setView(nextView);
    });
  };

  return { view, navigate };
}
