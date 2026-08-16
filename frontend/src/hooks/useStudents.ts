import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

// Every id that has ever started a conversation — powers StudentSelect's
// search dropdown. Not a real roster (no login exists in this
// prototype) — see stage3/api/students.py's module docstring.
export function useStudents() {
  const [students, setStudents] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listStudents()
      .then((r) => {
        if (!cancelled) setStudents(r.student_ids);
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

  return { students, loading, error, refetch: load };
}
