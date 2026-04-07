import { useEffect, useState } from "react";

import { api } from "../../lib/api";
import type { WorkspaceData } from "../../types/api";
import { sampleWorkspace } from "./sampleData";

interface WorkspaceState {
  data: WorkspaceData;
  error: string | null;
  isLoading: boolean;
  isSampleMode: boolean;
}

export function useProjectWorkspace(projectId: number | null) {
  const [state, setState] = useState<WorkspaceState>({
    data: sampleWorkspace,
    error: null,
    isLoading: true,
    isSampleMode: true,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;

    if (projectId === null || projectId < 0) {
      setState({
        data: sampleWorkspace,
        error: null,
        isLoading: false,
        isSampleMode: true,
      });
      return () => {
        cancelled = true;
      };
    }

    setState((current) => ({
      ...current,
      error: null,
      isLoading: true,
      isSampleMode: false,
    }));

    Promise.all([
      api.getAuthMe(),
      api.getSettingsOverview(),
      api.listAuditLogs(),
      api.getProjectOverview(projectId),
      api.listProjectChapters(projectId),
      api.listCharacters(projectId),
      api.listScenes(projectId),
      api.listVoices(projectId),
      api.listArtifacts(projectId),
      api.listStorageTargets(),
      api.listWorkflows(projectId),
      api.listProjectJobs(projectId),
      api.getMonitoring(),
      api.listProjectPreviews(projectId),
      api.getProjectInitialization(projectId),
      api.listPromptTemplates(projectId),
      api.listPromptFeedback(projectId),
      api.listMemories(projectId),
      api.listReviews(projectId),
    ])
      .then(
        ([
          authSession,
          settingsOverview,
          auditLogs,
          overview,
          chapters,
          characters,
          scenes,
          voices,
          artifacts,
          storageTargets,
          workflows,
          jobs,
          monitoring,
          previews,
          projectInitialization,
          promptTemplates,
          promptFeedback,
          sharedMemories,
          reviewTasks,
        ]) => {
        if (cancelled) {
          return;
        }
        setState({
          data: {
            authSession,
            settingsOverview,
            auditLogs: auditLogs.items,
            overview,
            chapters,
            characters,
            scenes,
            voices,
            artifacts,
            storageTargets: storageTargets.items,
            workflows,
            jobs,
            monitoring,
            previews,
            projectInitialization,
            promptTemplates,
            promptFeedback,
            sharedMemories,
            reviewTasks,
          },
          error: null,
          isLoading: false,
          isSampleMode: false,
        });
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setState({
          data: sampleWorkspace,
          error: error.message,
          isLoading: false,
          isSampleMode: true,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, nonce]);

  useEffect(() => {
    if (projectId === null || projectId < 0 || state.isSampleMode) {
      return undefined;
    }

    const hasActiveJobs = state.data.jobs.some((job) => job.status === "queued" || job.status === "running");
    if (!hasActiveJobs) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      setNonce((current) => current + 1);
    }, 3000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [projectId, state.data.jobs, state.isSampleMode]);

  return {
    ...state,
    reload: () => {
      setNonce((current) => current + 1);
    },
  };
}
