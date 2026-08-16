import { useState } from "react";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { useMastery } from "./hooks/useMastery";
import { StudentSelect } from "./components/StudentSelect/StudentSelect";
import { Sidebar } from "./components/Sidebar/Sidebar";
import { ConversationList } from "./components/ConversationList/ConversationList";
import { ChatThread } from "./components/ChatThread/ChatThread";
import "./App.css";

function App() {
  const [studentId, setStudentId] = useLocalStorage("stage3.studentId", "");
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<
    number | null
  >(null);
  // Shared "something changed, refetch" signal — bumped both when a new
  // conversation is created (existing behaviour) and after any chat
  // activity that might have moved a mastery estimate (diagnostic turns/
  // reassess — see ChatThread's onActivity). One counter, two dependents
  // (useConversations inside ConversationList, useMastery here), same
  // convention rather than a second parallel token.
  const [refreshToken, setRefreshToken] = useState(0);
  const { mastery } = useMastery(studentId, refreshToken);

  function handleSelectSubject(subject: string) {
    setSelectedSubject(subject);
    setSelectedConversationId(null);
  }

  return (
    <div className="app-shell">
      <div className="app-shell__topbar">
        <StudentSelect studentId={studentId} onChange={setStudentId} />
      </div>

      <div className="app-shell__sidebar">
        <Sidebar
          selectedSubject={selectedSubject}
          onSelectSubject={handleSelectSubject}
          mastery={mastery}
        />
      </div>

      <div className="app-shell__conversations">
        <ConversationList
          studentId={studentId}
          subject={selectedSubject}
          selectedConversationId={selectedConversationId}
          onSelectConversation={setSelectedConversationId}
          refreshToken={refreshToken}
          onConversationCreated={() => setRefreshToken((t) => t + 1)}
          mastery={mastery}
        />
      </div>

      <div className="app-shell__thread">
        <ChatThread
          conversationId={selectedConversationId}
          studentId={studentId}
          onActivity={() => setRefreshToken((t) => t + 1)}
        />
      </div>
    </div>
  );
}

export default App;
