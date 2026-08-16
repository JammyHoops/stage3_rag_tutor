import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation } from "../api/types";

export function useConversations(
  studentId: string,
  subject: string | null,
  refreshToken: number,
) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!studentId || !subject) {
      setConversations([]);
      return () => {};
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listConversations(studentId, subject)
      .then((r) => {
        if (!cancelled) setConversations(r.conversations);
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
  }, [studentId, subject]);

  useEffect(() => load(), [load, refreshToken]);

  return { conversations, loading, error, refetch: load };
}
