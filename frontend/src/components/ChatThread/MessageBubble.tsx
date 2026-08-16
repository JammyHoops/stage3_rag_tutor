import type { Message } from "../../api/types";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  return (
    <div
      className={
        "message-bubble message-bubble--" +
        (message.role === "student" ? "student" : "tutor")
      }
    >
      <div className="message-bubble__content">{message.content}</div>
      {/* Human-readable CC citations — see stage3/tutor/attribution.py.
          Replaces the old raw chunk_doc_ids dump (internal store IDs,
          not something a student/reviewer could act on). */}
      {message.attributions && message.attributions.length > 0 && (
        <div className="message-bubble__sources">
          Sources:{" "}
          {message.attributions.map((a, i) => (
            <span key={a.source_url}>
              {i > 0 && ", "}
              <a href={a.source_url} target="_blank" rel="noopener noreferrer">
                {a.title}
              </a>{" "}
              — {a.source_name} (
              <a href={a.licence_url} target="_blank" rel="noopener noreferrer">
                {a.licence}
              </a>
              )
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
