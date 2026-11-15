import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getHistory,
  resetAgent,
  sendMessage,
  type Agent,
  type HistoryTurn,
} from "../api";
import PortraitReel from "./PortraitReel";

type Turn = {
  id: string;
  who: "user" | "agent" | "error";
  text: string;
  tools: string[];
  meta?: string;
  when: Date;
};

type Props = {
  agent: Agent;
  onBack: () => void;
};

/** Ligne de détail sous une réponse : durée, volume, interruption. */
function metaLine(meta: HistoryTurn["meta"]): string | undefined {
  if (!meta) return undefined;
  const bits: string[] = [];
  if (meta.duration_ms) bits.push(`${(meta.duration_ms / 1000).toFixed(1)} s`);
  if (meta.output_tokens) bits.push(`${meta.output_tokens} tokens`);
  if (meta.interrupted) bits.push("interrompu");
  return bits.length ? bits.join(" · ") : undefined;
}

/** SQLite horodate en UTC sans suffixe ; le Z rétablit le fuseau local. */
function asDate(at: string): Date {
  return new Date(at.replace(" ", "T") + "Z");
}

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Aujourd'hui";
  if (d.toDateString() === yesterday.toDateString()) return "Hier";
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
}

const hhmm = (d: Date) =>
  d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function fromHistory(turn: HistoryTurn): Turn {
  return {
    id: `h${turn.id}`,
    who: turn.who,
    text: turn.text,
    tools: turn.tools,
    meta: metaLine(turn.meta),
    when: asDate(turn.at),
  };
}

export default function ChatView({ agent, onBack }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [activity, setActivity] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const poll = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (poll.current !== null) {
      window.clearInterval(poll.current);
      poll.current = null;
    }
  }, []);

  /** Un tour tourne côté serveur sans que cet onglet y soit attaché (page
   *  fermée puis rouverte) : on sonde la transcription jusqu'à la réponse. */
  const followPending = useCallback(() => {
    if (poll.current !== null) return;
    setBusy(true);
    setActivity("réponse en cours");
    poll.current = window.setInterval(async () => {
      try {
        const { turns: rows, pending } = await getHistory(agent.id);
        if (!pending) {
          stopPolling();
          setTurns(rows.map(fromHistory));
          setBusy(false);
          setActivity(null);
        }
      } catch {
        // Session expirée ou serveur arrêté : on cessera de sonder au
        // prochain échec visible de l'utilisateur.
        stopPolling();
        setBusy(false);
        setActivity(null);
      }
    }, 2500);
  }, [agent.id, stopPolling]);

  // Charge la transcription à l'ouverture de l'agent.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { turns: rows, pending } = await getHistory(agent.id);
        if (!alive) return;
        setTurns(rows.map(fromHistory));
        if (pending) followPending();
      } catch {
        /* le premier envoi resignalera le problème, avec un vrai message */
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [agent.id, followPending]);

  // Suit le bas du flux pendant que la réponse arrive.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, activity]);

  // En quittant l'agent : on détache ce client du flux et on arrête le
  // sondage. Le tour, lui, continue côté serveur — la réponse sera dans la
  // transcription au retour.
  useEffect(
    () => () => {
      abort.current?.abort();
      stopPolling();
    },
    [stopPolling],
  );

  async function submit() {
    const prompt = draft.trim();
    if (!prompt || busy) return;

    const userTurn: Turn = {
      id: `l${nextId.current++}`,
      who: "user",
      text: prompt,
      tools: [],
      when: new Date(),
    };
    const agentTurn: Turn = {
      id: `l${nextId.current++}`,
      who: "agent",
      text: "",
      tools: [],
      when: new Date(),
    };

    setTurns((t) => [...t, userTurn, agentTurn]);
    setDraft("");
    setBusy(true);
    setActivity("en route");
    setConfirmReset(false);

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
          onTool: (name) => {
            setActivity(`outil · ${name}`);
            patch((x) =>
              x.tools.includes(name)
                ? x
                : { ...x, tools: [...x.tools, name] },
            );
          },
          onDone: (info) => {
            setActivity(null);
            patch((x) => ({
              ...x,
              meta: metaLine(info as HistoryTurn["meta"]),
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
    stopPolling();
    await resetAgent(agent.id).catch(() => {});
    setTurns([]);
    setActivity(null);
    setBusy(false);
    setConfirmReset(false);
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
        {confirmReset ? (
          <div className="reset-confirm">
            <span>Tout oublier ?</span>
            <button className="link-btn" onClick={() => void handleReset()}>
              Oui
            </button>
            <button
              className="link-btn neutral"
              onClick={() => setConfirmReset(false)}
            >
              Non
            </button>
          </div>
        ) : (
          <button
            className="ghost-btn"
            onClick={() => setConfirmReset(true)}
            disabled={turns.length === 0}
            title="Efface la conversation et la mémoire de l'agent"
          >
            Nouveau fil
          </button>
        )}
      </div>

      <div className="log" ref={logRef}>
        {!loaded && <p className="empty">Chargement du fil…</p>}

        {loaded && turns.length === 0 && (
          <p className="empty">
            {agent.tagline}
            <br />
            <br />
            Le fil est conservé entre tes visites — même si tu fermes la page
            pendant une réponse. « Nouveau fil » repart de zéro.
          </p>
        )}

        {turns.map((turn, i) => (
          <div key={turn.id} className="turn-slot">
            {/* Séparateur quand le jour change — l'historique peut couvrir
                des semaines, les repères temporels comptent. */}
            {(i === 0 ||
              dayLabel(turns[i - 1].when) !== dayLabel(turn.when)) && (
              <div className="day-sep">
                <span>{dayLabel(turn.when)}</span>
              </div>
            )}
            <div className={`turn ${turn.who}`}>
              <span className="turn-who">
                {turn.who === "user"
                  ? "Toi"
                  : turn.who === "error"
                    ? "Échec"
                    : agent.name}
                <time>{hhmm(turn.when)}</time>
              </span>
              {(turn.text || turn.who !== "agent") && (
                <div className="bubble">
                  {turn.who === "user" ? (
                    turn.text
                  ) : (
                    // Agent et erreurs : les consignes d'échec contiennent
                    // des blocs de code à copier, autant les rendre aussi.
                    <div className="md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {turn.text}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}
              {(turn.meta || turn.tools.length > 0) && (
                <span className="meta-line">
                  {[turn.tools.join(" + "), turn.meta]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              )}
            </div>
          </div>
        ))}

        {activity && (
          <div className="activity">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
            {activity}
          </div>
        )}
      </div>

      <div className="composer">
        <textarea
          value={draft}
          placeholder={
            busy ? `${agent.name} travaille…` : `Écris à ${agent.name}…`
          }
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
