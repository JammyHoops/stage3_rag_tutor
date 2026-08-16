// Mirrors stage3/api response shapes exactly — see stage3/api/chat.py.

export interface Topic {
  id: string;
  label: string;
}

export type DiagnosticStatus = "pending" | "done";

export interface Conversation {
  id: number;
  student_id: string;
  subject: string;
  topic: string;
  created_at: string;
  updated_at: string;
  diagnostic_status: DiagnosticStatus;
  diagnostic_questions_asked: number;
}

export type MessageRole = "student" | "tutor";

// Human-readable CC citation — see stage3/tutor/attribution.py. Mirrors
// that module's dict exactly, no field renaming.
export interface Attribution {
  title: string;
  source_name: string;
  source_url: string;
  licence: string;
  licence_url: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: MessageRole;
  content: string;
  chunk_doc_ids: string[] | null;
  attributions: Attribution[] | null;
  created_at: string;
}

// Mirrors student_state/store.py::get_knowledge_state's row shape exactly.
export interface MasteryRow {
  student_id: string;
  subject: string;
  topic: string;
  estimate: number; // 0..1
  n_obs: number;
  updated_at: string;
}

export interface CreateConversationRequest {
  student_id: string;
  subject: string;
  topic: string;
}

export interface SendMessageRequest {
  student_id: string;
  text: string;
}

export interface SendMessageSuccess {
  answer: string;
  chunk_doc_ids: string[];
  attributions: Attribution[];
  tutor_message_id: number;
}

// Discriminated union: forces callers to branch on the (currently
// ever-present) 501 case rather than swallowing it in a generic catch.
export type SendMessageResult =
  | { ok: true; data: SendMessageSuccess }
  | { ok: false; status: number; detail: string };
