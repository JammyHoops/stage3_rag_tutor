import { useMemo, useState } from "react";
import { useTopics } from "../../hooks/useTopics";
import { useConversations } from "../../hooks/useConversations";
import { api, ApiError } from "../../api/client";
import { Spinner } from "../common/Spinner";
import { ErrorBanner } from "../common/ErrorBanner";
import { MasteryBar } from "../common/MasteryBar";
import type { MasteryRow } from "../../api/types";
import "./ConversationList.css";

interface ConversationListProps {
  studentId: string;
  subject: string | null;
  selectedConversationId: number | null;
  onSelectConversation: (id: number) => void;
  refreshToken: number;
  onConversationCreated: () => void;
  mastery: MasteryRow[];
}

// Every topic in the fixed taxonomy is directly clickable and IS its
// chat — no separate "New Chat" step. Clicking a topic resolves (or
// lazily creates, via a get-or-create backend call) its one continuous
// thread. See stage3/conversations/store.py's module docstring for the
// one-thread-per-topic decision this mirrors.
export function ConversationList({
  studentId,
  subject,
  selectedConversationId,
  onSelectConversation,
  refreshToken,
  onConversationCreated,
  mastery,
}: ConversationListProps) {
  const { topics, loading: topicsLoading, error: topicsError } = useTopics(subject);
  const { conversations, loading: convsLoading } = useConversations(
    studentId,
    subject,
    refreshToken,
  );
  const [pendingTopicId, setPendingTopicId] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [needsStudentId, setNeedsStudentId] = useState(false);

  const conversationByTopic = useMemo(() => {
    const map = new Map<string, (typeof conversations)[number]>();
    for (const c of conversations) map.set(c.topic, c);
    return map;
  }, [conversations]);

  const masteryByTopic = useMemo(() => {
    const map = new Map<string, MasteryRow>();
    if (!subject) return map;
    for (const row of mastery) {
      if (row.subject === subject) map.set(row.topic, row);
    }
    return map;
  }, [mastery, subject]);

  if (!subject) {
    return (
      <div className="conversation-list">
        <div className="conversation-list__empty">
          Select a subject to see its chats.
        </div>
      </div>
    );
  }

  async function handleTopicClick(topicId: string) {
    setCreateError(null);
    if (!studentId) {
      setNeedsStudentId(true);
      return;
    }
    setNeedsStudentId(false);

    const existing = conversationByTopic.get(topicId);
    if (existing) {
      onSelectConversation(existing.id);
      return;
    }

    setPendingTopicId(topicId);
    try {
      const conversation = await api.createConversation({
        student_id: studentId,
        subject: subject!,
        topic: topicId,
      });
      onSelectConversation(conversation.id);
      onConversationCreated(); // refetches so this topic's row is in the map next time
    } catch (e) {
      setCreateError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPendingTopicId(null);
    }
  }

  return (
    <div className="conversation-list">
      <div className="conversation-list__header">
        <span className="conversation-list__heading">{subject}</span>
      </div>

      {needsStudentId && (
        <div className="conversation-list__hint conversation-list__hint--info">
          Enter a Student ID above to start chatting.
        </div>
      )}
      {createError && <ErrorBanner message={`Couldn't open chat: ${createError}`} />}
      {(topicsLoading || convsLoading) && <Spinner />}
      {topicsError && (
        <ErrorBanner message={`Couldn't load topics: ${topicsError}`} />
      )}
      {!topicsLoading && !topicsError && topics.length === 0 && (
        <div className="conversation-list__empty">No topics configured.</div>
      )}

      <ul className="conversation-list__list">
        {topics.map((topic) => {
          const hasHistory = conversationByTopic.has(topic.id);
          const masteryRow = masteryByTopic.get(topic.id);
          return (
            <li key={topic.id}>
              <button
                type="button"
                className={
                  "conversation-list__item" +
                  (conversationByTopic.get(topic.id)?.id === selectedConversationId
                    ? " conversation-list__item--active"
                    : "")
                }
                onClick={() => handleTopicClick(topic.id)}
                disabled={pendingTopicId === topic.id}
              >
                <span className="conversation-list__item-label">{topic.label}</span>
                {masteryRow ? (
                  <MasteryBar estimate={masteryRow.estimate} nObs={masteryRow.n_obs} />
                ) : (
                  hasHistory && (
                    <span className="conversation-list__dot" aria-hidden="true" />
                  )
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
