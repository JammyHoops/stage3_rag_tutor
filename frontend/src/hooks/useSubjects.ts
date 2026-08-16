import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

export function useSubjects() {
  const [subjects, setSubjects] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listSubjects()
      .then((r) => {
        if (!cancelled) setSubjects(r.subjects);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  return { subjects, loading, error, refetch: load };
}
