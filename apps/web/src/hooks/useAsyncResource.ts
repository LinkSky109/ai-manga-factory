import { useEffect, useState } from "react";

export interface AsyncResourceState<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
}

export function useAsyncResource<T>(
  loader: () => Promise<T>,
  dependencies: ReadonlyArray<unknown>,
) {
  const [state, setState] = useState<AsyncResourceState<T>>({
    data: null,
    error: null,
    isLoading: true,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;

    setState((current) => ({
      data: current.data,
      error: null,
      isLoading: true,
    }));

    loader()
      .then((data) => {
        if (cancelled) {
          return;
        }
        setState({
          data,
          error: null,
          isLoading: false,
        });
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setState({
          data: null,
          error: error.message,
          isLoading: false,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [...dependencies, nonce]);

  return {
    ...state,
    reload: () => {
      setNonce((current) => current + 1);
    },
  };
}
