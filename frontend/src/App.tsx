import { useCallback, useEffect, useState } from "react";
import {
  deleteAgent,
  getAgents,
  getMe,
  logout,
  type Agent,
  type Device,
} from "./api";
import AgentForm from "./components/AgentForm";
import AgentGrid from "./components/AgentGrid";
import ChatView from "./components/ChatView";
import DevicePanel from "./components/DevicePanel";
import LoginGate from "./components/LoginGate";

type Phase = "checking" | "locked" | "ready";

export default function App() {
  const [phase, setPhase] = useState<Phase>("checking");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Record<string, string>>({});
  const [devices, setDevices] = useState<Device[]>([]);
  const [model, setModel] = useState("");
  const [active, setActive] = useState<Agent | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const me = await getMe();
      setDevices(me.devices);
      setModel(me.model);
      const listing = await getAgents();
      setAgents(listing.agents);
      setTools(listing.tools);
      setPhase("ready");
    } catch {
      // 401 attendu quand aucune session n'est ouverte.
      setPhase("locked");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete(agent: Agent) {
    await deleteAgent(agent.id);
    setAgents((current) => current.filter((a) => a.id !== agent.id));
    // Si la conversation ouverte portait sur cet agent, elle n'a plus d'objet.
    setActive((current) => (current?.id === agent.id ? null : current));
  }

  if (phase === "checking") {
    return <div className="loading">Initialisation…</div>;
  }

  if (phase === "locked") {
    return <LoginGate onUnlocked={() => void load()} />;
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="wordmark">
          <span>◆</span>
          Gordon
          <small>{model}</small>
        </div>
        <div className="topbar-spacer" />
        <button
          className="ghost-btn"
          onClick={async () => {
            await logout();
            setActive(null);
            setPhase("locked");
          }}
        >
          Verrouiller
        </button>
      </header>

      <main className="content">
        {active ? (
          <ChatView agent={active} onBack={() => setActive(null)} />
        ) : (
          <>
            <AgentGrid
              agents={agents}
              onSelect={setActive}
              onDelete={handleDelete}
              onNew={() => setCreating(true)}
            />
            <DevicePanel devices={devices} onChanged={() => void load()} />
          </>
        )}
      </main>

      {creating && (
        <AgentForm
          tools={tools}
          onCancel={() => setCreating(false)}
          onCreated={(agent) => {
            setAgents((current) => [...current, agent]);
            setCreating(false);
          }}
        />
      )}
    </div>
  );
}
