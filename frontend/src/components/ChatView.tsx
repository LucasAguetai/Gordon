import { useEffect, useRef, useState } from "react";
import { resetAgent, sendMessage, type Agent } from "../api";
import PortraitReel from "./PortraitReel";

type Turn = {
  id: number;
  who: "user" | "agent" | "error";
  text: string;
  meta?: string;
};

type Props = {
  agent: Agent;
  onBack: () => void;
};

export default function ChatView({ agent, onBack }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);

  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);
  const abort = useRef<AbortController | null>(null);

  // Suit le bas du flux pendant que la réponse arrive.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, activity]);

  // Annule la requête en cours si on quitte l'agent, pour ne pas laisser un
  // flux ouvert et une mise à jour d'état sur un composant démonté.
  useEffect(() => () => abort.current?.abort(), []);

  async function submit() {
    const prompt = draft.trim();
    if (!prompt || busy) return;

    const userTurn: Turn = { id: nextId.current++, who: "user", text: prompt };
    const agentTurn: Turn = { id: nextId.current++, who: "agent", text: "" };

    setTurns((t) => [...t, userTurn, agentTurn]);
    setDraft("");
    setBusy(true);
    setActivity("en route");

    const controller = new AbortController();
    abort.current = controller;

    const patch = (fn: (turn: Turn) => Turn) =>
      setTurns((t) => t.map((x) => (x.id === agentTurn.id ? fn(x) : x)));

    try {
      await sendMessage(
        agent.id,
        prompt,
        {
          onText: (chunk) => {
            setActivity(null);
            patch((x) => ({ ...x, text: x.text + chunk }));
          },
          onThinking: () => setActivity("réflexion"),
          onTool: (name) => setActivity(`outil · ${name}`),
          onDone: (info) => {
            setActivity(null);
            const ms = Number(info.duration_ms ?? 0);
            const out = info.output_tokens;
            const bits = [`${(ms / 1000).toFixed(1)} s`];
            if (out) bits.push(`${out} tokens`);
            patch((x) => ({
              ...x,
              meta: bits.join(" · "),
              // Un tour peut se terminer sans texte (ex. refus d'outil).
              text: x.text || "(aucune réponse)",
            }));
          },
          onError: (message) => {
            setActivity(null);
            patch((x) => ({ ...x, who: "error", text: message }));
          },
        },
        controller.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setActivity(null);
        patch((x) => ({
          ...x,
          who: "error",
          text: (e as Error).message || "Connexion interrompue.",
        }));
      }
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }

  async function handleReset() {
    abort.current?.abort();
    await resetAgent(agent.id).catch(() => {});
    setTurns([]);
    setActivity(null);
    setBusy(false);
  }

  return (
    <div className="chat" style={{ ["--accent" as string]: agent.accent }}>
      <div className="chat-head">
        <button className="ghost-btn" onClick={onBack}>
          ← Équipe
        </button>
        <div className="chat-badge">
          <PortraitReel
            look={agent.look}
            accent={agent.accent}
            id={agent.id}
            state="uniform"
            size={44}
            instant
          />
        </div>
        <div className="chat-id">
          <h1>{agent.name}</h1>
          <p>
            {agent.callsign} · {agent.role}
          </p>
        </div>
        <div className="topbar-spacer" />
        <button
          className="ghost-btn"
          onClick={handleReset}
          disabled={turns.length === 0}
          title="Oublie le fil de cette conversation"
        >
          Nouveau fil
        </button>
      </div>

      <div className="log" ref={logRef}>
        {turns.length === 0 && (
          <p className="empty">
            {agent.tagline}
            <br />
            <br />
            Le fil est conservé entre tes visites. « Nouveau fil » repart de
            zéro.
          </p>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className={`turn ${turn.who}`}>
            <span className="turn-who">
              {turn.who === "user"
                ? "Toi"
                : turn.who === "error"
                  ? "Échec"
                  : agent.name}
            </span>
            {(turn.text || turn.who !== "agent") && (
              <div className="bubble">{turn.text}</div>
            )}
            {turn.meta && <span className="meta-line">{turn.meta}</span>}
          </div>
        ))}

        {activity && (
          <div className="activity">
            <span className="pulse" />
            {activity}
          </div>
        )}
      </div>

      <div className="composer">
        <textarea
          value={draft}
          placeholder={`Écris à ${agent.name}…`}
          rows={1}
          onChange={(e) => {
            setDraft(e.target.value);
            // Hauteur suivant le contenu, plafonnée par le CSS.
            e.target.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <button
          className="send-btn"
          onClick={() => void submit()}
          disabled={busy || draft.trim().length === 0}
        >
          {busy ? "…" : "Envoyer"}
        </button>
      </div>
    </div>
  );
}
