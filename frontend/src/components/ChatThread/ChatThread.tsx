import { useState } from "react";
import { useMessages } from "../../hooks/useMessages";
import { useConversation } from "../../hooks/useConversation";
import { api, ApiError } from "../../api/client";
import { MessageBubble } from "./MessageBubble";
import { MessageComposer } from "./MessageComposer";
import { Spinner } from "../common/Spinner";
import { ErrorBanner } from "../common/ErrorBanner";
import "./ChatThread.css";

interface ChatThreadProps {
  conversationId: number | null;
  studentId: string;
  // Called after a successful send/reassess — a diagnostic round may have
  // just completed, which is the only thing that changes mastery data.
  // Cheap to over-call (mastery fetch is a small SQLite read), simpler
  // than detecting exactly when a diagnostic round finishes.
  onActivity?: () => void;
}

type SendState = "idle" | "sending" | "error501" | "error";

// Must match stage3/tutor/diagnostic.py::QUESTION_COUNT — no shared
// config source between frontend/backend today, so this is duplicated
// deliberately rather than guessed; keep them in sync by hand.
const DIAGNOSTIC_QUESTION_COUNT = 3;

export function ChatThread({ conversationId, studentId, onActivity }: ChatThreadProps) {
  const { messages, loading, error, refetch } = useMessages(conversationId);
  const { conversation, refetch: refetchConversation } = useConversation(conversationId);
  const [sendState, setSendState] = useState<SendState>("idle");
  const [lastErrorDetail, setLastErrorDetail] = useState<string | null>(null);
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [reassessing, setReassessing] = useState(false);
  const [reassessError, setReassessError] = useState<string | null>(null);
  // Bumped whenever we want to force the (uncontrolled-ish) composer to
  // reset its draft to a specific value — e.g. restoring text after a 501
  // so the student doesn't have to retype it.
  const [composerResetToken, setComposerResetToken] = useState(0);

  if (conversationId === null) {
    return (
      <div className="chat-thread chat-thread--empty">
        Select or start a chat.
      </div>
    );
  }

  const isDiagnosticPending = conversation?.diagnostic_status === "pending";

  async function handleSend(text: string) {
    if (conversationId === null) return;
    setSendState("sending");
    setPendingText(text);
    setLastErrorDetail(null);

    const result = await api.sendMessage(conversationId, {
      student_id: studentId,
      text,
    });

    if (result.ok) {
      setPendingText(null);
      setSendState("idle");
      await refetch(); // pulls the real persisted rows (real ids/timestamps)
      await refetchConversation(); // diagnostic progress may have changed
      onActivity?.(); // mastery may have changed too — see prop docstring
    } else if (result.status === 501) {
      // Nothing was persisted server-side — the same fail-closed pattern
      // as before, now only reachable via a still-unimplemented stub
      // (e.g. profile_to_note for a student with a real Stage 1 profile —
      // not exercised today, no such data ingested).
      setSendState("error501");
      setLastErrorDetail(result.detail);
      setComposerResetToken((t) => t + 1);
    } else {
      setSendState("error");
      setLastErrorDetail(result.detail);
      setComposerResetToken((t) => t + 1);
    }
  }

  async function handleReassess() {
    if (conversationId === null) return;
    setReassessing(true);
    setReassessError(null);
    try {
      await api.reassessConversation(conversationId);
      await refetch();
      await refetchConversation();
      onActivity?.();
    } catch (e) {
      setReassessError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setReassessing(false);
    }
  }

  return (
    <div className="chat-thread">
      <div className="chat-thread__header">
        <button
          type="button"
          className="chat-thread__reassess-btn"
          onClick={handleReassess}
          disabled={reassessing || isDiagnosticPending}
          title="Start a fresh quick check-in to update your mastery estimate for this topic"
        >
          {reassessing ? "Starting…" : "Re-check my understanding"}
        </button>
      </div>
      {reassessError && (
        <ErrorBanner message={`Couldn't start check-in: ${reassessError}`} />
      )}

      <div className="chat-thread__messages">
        {loading && <Spinner />}
        {error && <ErrorBanner message={`Couldn't load messages: ${error}`} />}
        {!loading && !error && messages.length === 0 && (
          <div className="chat-thread__empty-hint">
            No messages yet — say hello.
          </div>
        )}
        {isDiagnosticPending && (
          <div className="chat-thread__status chat-thread__status--info">
            Quick check-in — question {Math.min(
              (conversation?.diagnostic_questions_asked ?? 0) + 1,
              DIAGNOSTIC_QUESTION_COUNT,
            )} of {DIAGNOSTIC_QUESTION_COUNT}. This is a low-stakes way for
            the tutor to see where you're starting from.
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}

        {sendState === "sending" && (
          <div className="chat-thread__status chat-thread__status--sending">
            <Spinner /> Sending…
          </div>
        )}
        {sendState === "error501" && (
          <div className="chat-thread__status chat-thread__status--info">
            Not sent — a part of the tutor's response pipeline isn't
            implemented yet. Your message was not saved, so nothing is lost.
            <button type="button" onClick={() => setSendState("idle")}>
              Dismiss
            </button>
          </div>
        )}
        {sendState === "error" && (
          <div className="chat-thread__status chat-thread__status--error">
            Failed to send: {lastErrorDetail}
            <button
              type="button"
              onClick={() => pendingText && handleSend(pendingText)}
            >
              Retry
            </button>
          </div>
        )}
      </div>

      <MessageComposer
        key={composerResetToken}
        disabled={sendState === "sending"}
        onSend={handleSend}
        initialDraft={
          sendState === "error501" || sendState === "error"
            ? (pendingText ?? undefined)
            : undefined
        }
      />
    </div>
  );
}
