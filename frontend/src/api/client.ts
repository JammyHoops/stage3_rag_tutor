import type {
  Conversation,
  CreateConversationRequest,
  MasteryRow,
  Message,
  SendMessageRequest,
  SendMessageResult,
  SendMessageSuccess,
  Topic,
} from "./types";

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function safeJson(res: Response): Promise<{ detail?: string } | null> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    const body = await safeJson(res);
    throw new ApiError(res.status, body?.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const parsed = await safeJson(res);
    throw new ApiError(res.status, parsed?.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJson<{ ok: boolean }>("/health"),

  listSubjects: () => getJson<{ subjects: string[] }>("/subjects"),

  listTopics: (subject: string) =>
    getJson<{ subject: string; topics: Topic[] }>(
      `/subjects/${encodeURIComponent(subject)}/topics`,
    ),

  // Every id that has ever started a conversation — not a real roster
  // (no login exists), just search-assist for the student picker. See
  // stage3/api/students.py's module docstring.
  listStudents: () => getJson<{ student_ids: string[] }>("/students"),

  getMastery: (studentId: string, subject?: string) => {
    const params = subject ? `?subject=${encodeURIComponent(subject)}` : "";
    return getJson<{ mastery: MasteryRow[] }>(
      `/students/${encodeURIComponent(studentId)}/mastery${params}`,
    );
  },

  // Refreshed by ChatThread after every turn so diagnostic_status /
  // diagnostic_questions_asked stay current (they change over the life
  // of a thread, unlike most other conversation fields).
  getConversation: (conversationId: number) =>
    getJson<Conversation>(`/conversations/${conversationId}`),

  listConversations: (studentId: string, subject?: string) => {
    const params = new URLSearchParams({ student_id: studentId });
    if (subject) params.set("subject", subject);
    return getJson<{ conversations: Conversation[] }>(
      `/conversations?${params.toString()}`,
    );
  },

  createConversation: (body: CreateConversationRequest) =>
    postJson<Conversation>("/conversations", body),

  // Starts a fresh diagnostic round on an EXISTING thread (appended to
  // it, not a new conversation) — see stage3/api/chat.py's /reassess
  // endpoint and conversations/store.py::reset_diagnostic.
  reassessConversation: (conversationId: number) =>
    postJson<Conversation>(`/conversations/${conversationId}/reassess`, {}),

  listMessages: (conversationId: number) =>
    getJson<{ messages: Message[] }>(
      `/conversations/${conversationId}/messages`,
    ),

  // Deliberately does NOT throw on 501 — that response is an expected,
  // handled outcome of this prototype's current backend state (redaction
  // is a fail-closed stub), not a client error. Only genuine transport/
  // parse failures or other HTTP errors throw.
  sendMessage: async (
    conversationId: number,
    body: SendMessageRequest,
  ): Promise<SendMessageResult> => {
    const res = await fetch(
      `${BASE_URL}/conversations/${conversationId}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const parsed = await safeJson(res);
    if (res.ok) {
      return { ok: true, data: parsed as SendMessageSuccess };
    }
    return {
      ok: false,
      status: res.status,
      detail: parsed?.detail ?? res.statusText,
    };
  },
};
