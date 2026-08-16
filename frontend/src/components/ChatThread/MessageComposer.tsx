import { useState } from "react";
import type { KeyboardEvent } from "react";

interface MessageComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
  initialDraft?: string;
}

export function MessageComposer({
  disabled,
  onSend,
  initialDraft,
}: MessageComposerProps) {
  const [draft, setDraft] = useState(initialDraft ?? "");

  function submit() {
    const text = draft.trim();
    if (!text || disabled) return;
    onSend(text);
    setDraft("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="message-composer">
      <textarea
        className="message-composer__input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message… (Enter to send, Shift+Enter for a new line)"
        disabled={disabled}
        rows={2}
      />
      <button
        type="button"
        className="message-composer__send-btn"
        onClick={submit}
        disabled={disabled || !draft.trim()}
      >
        Send
      </button>
    </div>
  );
}
