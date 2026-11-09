import { useState } from "react";
import type { Agent } from "../api";
import PortraitReel from "./PortraitReel";

type Props = {
  agents: Agent[];
  onSelect: (agent: Agent) => void;
  onDelete: (agent: Agent) => Promise<void>;
  onNew: () => void;
};

export default function AgentGrid({ agents, onSelect, onDelete, onNew }: Props) {
  // Agent dont la suppression attend confirmation.
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function remove(agent: Agent) {
    setBusy(agent.id);
    try {
      await onDelete(agent);
    } finally {
      setBusy(null);
      setConfirming(null);
    }
  }

  return (
    <>
      <div className="section-head">
        <h2>Spécialités</h2>
        <hr />
      </div>

      <div className="grid">
        {agents.map((agent) => (
          <article
            key={agent.id}
            className="frame"
            style={{ ["--accent" as string]: agent.accent }}
          >
            {/* Zone cliquable en fond : un bouton imbriqué dans un bouton
                serait du HTML invalide, et la suppression doit rester
                distincte de l'ouverture. */}
            <button
              className="frame-hit"
              aria-label={`Ouvrir ${agent.name}`}
              onClick={() => onSelect(agent)}
            />

            <span className="callsign">{agent.callsign}</span>

            <div className="frame-portrait">
              <PortraitReel
                look={agent.look}
                accent={agent.accent}
                id={agent.id}
                state="uniform"
                size={96}
                instant
              />
            </div>

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

            {confirming === agent.id ? (
              <div className="frame-confirm">
                <span>Supprimer {agent.name} et son fil ?</span>
                <div>
                  <button
                    className="link-btn"
                    disabled={busy === agent.id}
                    onClick={() => void remove(agent)}
                  >
                    {busy === agent.id ? "…" : "Supprimer"}
                  </button>
                  <button
                    className="link-btn neutral"
                    onClick={() => setConfirming(null)}
                  >
                    Annuler
                  </button>
                </div>
              </div>
            ) : (
              <button
                className="frame-del"
                title={`Supprimer ${agent.name}`}
                aria-label={`Supprimer ${agent.name}`}
                onClick={() => setConfirming(agent.id)}
              >
                ✕
              </button>
            )}
          </article>
        ))}

        <button className="frame frame-new" onClick={onNew}>
          <span className="plus">+</span>
          <span className="frame-name">Nouvel agent</span>
          <p className="frame-tagline">
            Une spécialité, des outils, un prompt.
          </p>
        </button>
      </div>
    </>
  );
}
