import { useState } from "react";
import { createAgent, type Agent } from "../api";
import { randomLook, type Look } from "../avatar";
import PortraitReel from "./PortraitReel";

type Props = {
  tools: Record<string, string>;
  onCreated: (agent: Agent) => void;
  onCancel: () => void;
};

const ACCENTS = [
  "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#38bdf8",
  "#fb923c", "#4ade80", "#f87171", "#22d3ee", "#c084fc",
];

const EFFORTS = [
  ["low", "Rapide"],
  ["medium", "Équilibré"],
  ["high", "Approfondi"],
  ["xhigh", "Très approfondi"],
] as const;

const PLACEHOLDER = `Tu es <nom>, spécialiste de <domaine>.

Tu réponds en français. Va droit au but : pas de préambule.
Quand tu n'es pas sûr d'un fait, dis-le plutôt que de deviner.

Méthode :
- ...`;

export default function AgentForm({ tools, onCreated, onCancel }: Props) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [tagline, setTagline] = useState("");
  const [accent, setAccent] = useState(ACCENTS[4]);
  const [picked, setPicked] = useState<string[]>([]);
  const [effort, setEffort] = useState<string>("high");
  const [prompt, setPrompt] = useState("");
  const [look, setLook] = useState<Look>(() => randomLook());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleTool(tool: string) {
    setPicked((current) =>
      current.includes(tool)
        ? current.filter((t) => t !== tool)
        : [...current, tool],
    );
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const { agent } = await createAgent({
        name,
        role,
        tagline,
        accent,
        tools: picked,
        system_prompt: prompt,
        look,
        effort,
      });
      onCreated(agent);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const ready = name.trim() && role.trim() && prompt.trim();

  return (
    <div className="sheet-backdrop" onClick={onCancel}>
      <div
        className="sheet"
        style={{ ["--accent" as string]: accent }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-head">
          <h2>Nouvel agent</h2>
          <button className="ghost-btn" onClick={onCancel}>
            Annuler
          </button>
        </div>

        <div className="sheet-body">
          <div className="sheet-portrait">
            <div className="frame-portrait">
              <PortraitReel
                look={look}
                accent={accent}
                id="preview"
                state="uniform"
                size={96}
                instant
              />
            </div>
            <button className="ghost-btn" onClick={() => setLook(randomLook())}>
              Autre visage
            </button>
          </div>

          <div className="sheet-fields">
            <label>
              <span>Nom</span>
              <input
                value={name}
                maxLength={40}
                placeholder="Atlas"
                onChange={(e) => setName(e.target.value)}
              />
            </label>

            <label>
              <span>Spécialité</span>
              <input
                value={role}
                maxLength={40}
                placeholder="Finance"
                onChange={(e) => setRole(e.target.value)}
              />
            </label>

            <label className="wide">
              <span>Accroche</span>
              <input
                value={tagline}
                maxLength={120}
                placeholder="Budget, dépenses, épargne."
                onChange={(e) => setTagline(e.target.value)}
              />
            </label>

            <div className="wide">
              <span className="field-label">Couleur</span>
              <div className="swatches">
                {ACCENTS.map((c) => (
                  <button
                    key={c}
                    className={`swatch${c === accent ? " on" : ""}`}
                    style={{ background: c }}
                    aria-label={c}
                    onClick={() => setAccent(c)}
                  />
                ))}
              </div>
            </div>

            <div className="wide">
              <span className="field-label">
                Outils
                <small>
                  Ne donne que le nécessaire : la liste est appliquée côté
                  serveur, l'agent ne peut pas en sortir.
                </small>
              </span>
              <div className="checks">
                {Object.entries(tools).map(([tool, label]) => (
                  <label key={tool} className="check">
                    <input
                      type="checkbox"
                      checked={picked.includes(tool)}
                      onChange={() => toggleTool(tool)}
                    />
                    <code>{tool}</code>
                    <small>{label}</small>
                  </label>
                ))}
              </div>
            </div>

            <div className="wide">
              <span className="field-label">Profondeur de réflexion</span>
              <div className="segmented">
                {EFFORTS.map(([value, label]) => (
                  <button
                    key={value}
                    className={value === effort ? "on" : ""}
                    onClick={() => setEffort(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <label className="wide">
              <span className="field-label">
                Prompt système
                <small>Définit le métier de l'agent et sa méthode.</small>
              </span>
              <textarea
                value={prompt}
                rows={9}
                placeholder={PLACEHOLDER}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </label>
          </div>
        </div>

        {error && <p className="alert">{error}</p>}

        <div className="sheet-foot">
          <button
            className="primary-btn"
            disabled={!ready || busy}
            onClick={() => void submit()}
          >
            {busy ? "Création…" : "Créer l'agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
