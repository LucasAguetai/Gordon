import { useCallback, useEffect, useState } from "react";
import {
  deleteAgent,
  getAgents,
  getMe,
  logout,
  type Agent,
  type Device,
  type ToolMeta,
} from "./api";
import AgentForm from "./components/AgentForm";
import AgentGrid from "./components/AgentGrid";
import ApplePanel from "./components/ApplePanel";
import AppleView from "./components/AppleView";
import ChatView from "./components/ChatView";
import DevicePanel from "./components/DevicePanel";
import EngineConnect from "./components/EngineConnect";
import EnginePanel from "./components/EnginePanel";
import LoginGate from "./components/LoginGate";

type Phase = "checking" | "locked" | "ready";

export default function App() {
  const [phase, setPhase] = useState<Phase>("checking");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Record<string, ToolMeta>>({});
  const [devices, setDevices] = useState<Device[]>([]);
  const [model, setModel] = useState("");
  const [active, setActive] = useState<Agent | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Agent | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [appleOpen, setAppleOpen] = useState(false);
  // Incrémenté à chaque connexion réussie : le panneau Moteur se recharge.
  const [engineEpoch, setEngineEpoch] = useState(0);

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
          <ChatView
            agent={active}
            onBack={() => setActive(null)}
            onConnectEngine={() => setConnecting(true)}
          />
        ) : appleOpen ? (
          <AppleView
            agents={agents}
            tools={tools}
            onBack={() => setAppleOpen(false)}
          />
        ) : (
          <>
            <AgentGrid
              agents={agents}
              tools={tools}
              onSelect={setActive}
              onEdit={setEditing}
              onDelete={handleDelete}
              onNew={() => setCreating(true)}
            />
            <ApplePanel onManage={() => setAppleOpen(true)} />
            <EnginePanel
              onConnect={() => setConnecting(true)}
              refreshKey={engineEpoch}
            />
            <DevicePanel devices={devices} onChanged={() => void load()} />
          </>
        )}
      </main>

      {connecting && (
        <EngineConnect
          onCancel={() => setConnecting(false)}
          onDone={() => {
            setConnecting(false);
            setEngineEpoch((n) => n + 1);
          }}
        />
      )}

      {creating && (
        <AgentForm
          tools={tools}
          onCancel={() => setCreating(false)}
          onSaved={(agent) => {
            setAgents((current) => [...current, agent]);
            setCreating(false);
          }}
        />
      )}

      {editing && (
        <AgentForm
          tools={tools}
          initial={editing}
          onCancel={() => setEditing(null)}
          onSaved={(agent) => {
            setAgents((current) =>
              current.map((a) => (a.id === agent.id ? agent : a)),
            );
            // Si la conversation ouverte porte sur cet agent, elle doit
            // refléter la fiche à jour (nom, couleur, outils).
            setActive((current) => (current?.id === agent.id ? agent : current));
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
