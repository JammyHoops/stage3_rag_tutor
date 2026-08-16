import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation } from "../api/types";

// Single-conversation fetch, refetchable — distinct from useConversations
// (plural, list-scoped). Used by ChatThread to keep diagnostic_status /
// diagnostic_questions_asked current after every turn.
export function useConversation(conversationId: number | null) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (conversationId === null) {
      setConversation(null);
      return () => {};
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getConversation(conversationId)
      .then((c) => {
        if (!cancelled) setConversation(c);
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
  }, [conversationId]);

  useEffect(() => load(), [load]);

  return { conversation, loading, error, refetch: load };
}
