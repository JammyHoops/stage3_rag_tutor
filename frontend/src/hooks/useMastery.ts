import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { MasteryRow } from "../api/types";

// Same shape/convention as useConversations.ts: skips the fetch for an
// empty studentId, refetches on refreshToken bump. Fetches ALL subjects
// at once (small dataset — see student_state/store.py) and lets Sidebar/
// ConversationList each derive their own per-subject/per-topic view from
// the one list, rather than fetching per-subject repeatedly.
export function useMastery(studentId: string, refreshToken: number) {
  const [mastery, setMastery] = useState<MasteryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!studentId) {
      setMastery([]);
      return () => {};
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getMastery(studentId)
      .then((r) => {
        if (!cancelled) setMastery(r.mastery);
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
  }, [studentId]);

  useEffect(() => load(), [load, refreshToken]);

  return { mastery, loading, error, refetch: load };
}
