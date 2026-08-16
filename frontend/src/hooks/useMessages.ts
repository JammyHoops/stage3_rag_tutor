import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Message } from "../api/types";

export function useMessages(conversationId: number | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (conversationId === null) {
      setMessages([]);
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return api
      .listMessages(conversationId)
      .then((r) => setMessages(r.messages))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    load();
  }, [load]);

  return { messages, loading, error, refetch: load };
}
