import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Topic } from "../api/types";

export function useTopics(subject: string | null) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!subject) {
      setTopics([]);
      return () => {};
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listTopics(subject)
      .then((r) => {
        if (!cancelled) setTopics(r.topics);
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
  }, [subject]);

  useEffect(() => load(), [load]);

  return { topics, loading, error, refetch: load };
}
