import type { Agent } from "../api";
import { hasPortrait } from "../portraits";
import PortraitReel from "./PortraitReel";

type Props = {
  agents: Agent[];
  onSelect: (agent: Agent) => void;
};

export default function AgentGrid({ agents, onSelect }: Props) {
  return (
    <>
      <div className="section-head">
        <h2>Spécialités</h2>
        <hr />
      </div>

      <div className="grid">
        {agents.map((agent) => (
          <button
            key={agent.id}
            className="frame"
            style={{ ["--accent" as string]: agent.accent }}
            onClick={() => onSelect(agent)}
          >
            <span className="callsign">{agent.callsign}</span>

            {hasPortrait(agent.id) && (
              <div className="frame-portrait">
                <PortraitReel agentId={agent.id} state="uniform" size={64} instant />
              </div>
            )}

            <div className="frame-role">{agent.role}</div>
            <h3 className="frame-name">{agent.name}</h3>
            <p className="frame-tagline">{agent.tagline}</p>
            <div className="frame-tools">
              {agent.tools.length === 0 ? (
                <span className="tool-chip">conversation seule</span>
              ) : (
                agent.tools.map((tool) => (
                  <span className="tool-chip" key={tool}>
                    {tool}
                  </span>
                ))
              )}
            </div>
          </button>
        ))}
      </div>
    </>
  );
}
