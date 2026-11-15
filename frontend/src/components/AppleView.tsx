import { useCallback, useEffect, useRef, useState } from "react";
import {
  appleOpenSettings,
  appleRequestAccess,
  getApple,
  type Agent,
  type AppleOverview,
  type ToolMeta,
} from "../api";

type Props = {
  agents: Agent[];
  tools: Record<string, ToolMeta>;
  onBack: () => void;
};

const BADGES: Record<string, { label: string; tone: string }> = {
  accorde: { label: "Accordé", tone: "ok" },
  ecriture_seule: { label: "Écriture seule", tone: "warn" },
  a_tester: { label: "À tester", tone: "warn" },
  non_demande: { label: "Jamais demandé", tone: "muted" },
  refuse: { label: "Refusé", tone: "bad" },
  restreint: { label: "Restreint", tone: "bad" },
};

const DOMAINS = [
  {
    key: "calendriers",
    title: "Calendriers",
    text: "Lire les évènements, en créer. Jamais de modification ni de suppression.",
  },
  {
    key: "rappels",
    title: "Rappels",
    text: "Lire les rappels, en créer. Impossible de cocher ou supprimer.",
  },
  {
    key: "mail",
    title: "Mail (Automatisation)",
    text: "Chercher et lire la boîte de réception, préparer des brouillons. L'envoi reste un geste humain.",
  },
] as const;

/**
 * Page de gestion des accès Apple.
 *
 * Son premier rôle est d'expliquer la nature du lien : Gordon ne connaît
 * pas le compte iCloud — il lit les applications du Mac, et chaque accès
 * est une autorisation macOS, visible et révocable dans les Réglages.
 */
export default function AppleView({ agents, tools, onBack }: Props) {
  const [data, setData] = useState<AppleOverview | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const poll = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getApple());
    } catch {
      /* la page restera sur « chargement » ; rien à casser */
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      if (poll.current !== null) window.clearInterval(poll.current);
    };
  }, [load]);

  /** Lance la demande système puis guette la décision : la fenêtre
   *  s'affiche sur le Mac, pas dans ce navigateur. */
  async function request(domain: string) {
    setAsking(domain);
    await appleRequestAccess(domain).catch(() => {});
    const before = statusOf(domain);
    poll.current = window.setInterval(async () => {
      await load();
      // L'état est relu dans le setData ; on vérifie à la prochaine passe.
    }, 2000);
    // Coupe le sondage dès que la décision tombe, ou au bout de 3 minutes.
    const deadline = Date.now() + 180_000;
    const watch = window.setInterval(() => {
      if (statusRef.current(domain) !== before || Date.now() > deadline) {
        if (poll.current !== null) window.clearInterval(poll.current);
        window.clearInterval(watch);
        poll.current = null;
        setAsking(null);
      }
    }, 1000);
  }

  function statusOf(domain: string): string {
    const d = data?.[domain as "calendriers" | "rappels" | "mail"];
    return d?.status ?? "inconnu";
  }

  // request() compare l'état AVANT la demande à l'état courant : il lui faut
  // une lecture toujours fraîche, hors de la fermeture de l'intervalle.
  const statusRef = useRef(statusOf);
  statusRef.current = statusOf;

  const appleAgents = agents.filter((a) =>
    a.tools.some((t) => tools[t]?.group === "apple"),
  );

  return (
    <div className="apple-view">
      <div className="chat-head">
        <button className="ghost-btn" onClick={onBack}>
          ← Accueil
        </button>
        <div className="chat-id">
          <h1>Connexion Apple</h1>
          <p>Agenda · Rappels · Mail</p>
        </div>
      </div>

      <section className="apple-intro">
        <p>
          Gordon n'est <strong>pas relié à ton compte Apple</strong> : il ne
          connaît ni ton identifiant ni ton mot de passe iCloud, et ne parle
          jamais aux serveurs d'Apple. Ses outils lisent les applications du
          Mac qui l'héberge — Calendrier, Rappels, Mail — qui se synchronisent
          elles-mêmes avec iCloud, comme d'habitude.
        </p>
        <p>
          Chaque accès est une <strong>autorisation macOS</strong>, accordée à
          l'application qui lance le serveur (ton terminal), jamais à un site
          ou à un service distant. Tout se voit et se révoque dans Réglages
          Système → Confidentialité et sécurité. Dernier verrou : un agent ne
          peut utiliser un outil Apple que si sa fiche le lui donne.
        </p>
      </section>

      {!data && <p className="empty">Lecture des autorisations…</p>}
      {data && !data.available && (
        <p className="empty">
          Les outils Apple sont inactifs sur cette machine (macOS requis, ou
          GORDON_APPLE_TOOLS=false).
        </p>
      )}

      {data?.available && (
        <div className="apple-cards">
          {DOMAINS.map(({ key, title, text }) => {
            const domain = data[key];
            const badge = BADGES[domain?.status ?? ""] ?? {
              label: domain?.status ?? "Inconnu",
              tone: "muted",
            };
            const canAsk =
              domain?.status === "non_demande" || domain?.status === "a_tester";
            return (
              <article className="apple-card" key={key}>
                <header>
                  <h3>{title}</h3>
                  <span className={`badge badge-${badge.tone}`}>
                    {badge.label}
                  </span>
                </header>
                <p>{text}</p>

                {domain?.noms && domain.noms.length > 0 && (
                  <div className="apple-names">
                    {domain.noms.map((name) => (
                      <span className="tool-chip" key={name}>
                        {name}
                      </span>
                    ))}
                  </div>
                )}

                <div className="apple-actions">
                  {canAsk && (
                    <button
                      className="ghost-btn"
                      disabled={asking !== null}
                      onClick={() => void request(key)}
                    >
                      {asking === key
                        ? "Regarde l'écran du Mac…"
                        : key === "mail"
                          ? "Tester l'accès"
                          : "Demander l'accès"}
                    </button>
                  )}
                  <button
                    className="link-btn neutral"
                    onClick={() => void appleOpenSettings(key).catch(() => {})}
                  >
                    Réglages macOS
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <section className="apple-agents">
        <h3>Qui s'en sert ?</h3>
        {appleAgents.length === 0 ? (
          <p className="engine-note">
            Aucun agent n'a d'outil Apple pour l'instant. Donne-les en
            modifiant un agent (✎) — chaque case cochée n'ouvre que l'accès
            qu'elle décrit.
          </p>
        ) : (
          appleAgents.map((agent) => (
            <div className="device-row" key={agent.id}>
              <span
                className="apple-agent-name"
                style={{ color: agent.accent }}
              >
                {agent.name}
              </span>
              <span className="grow apple-agent-tools">
                {agent.tools
                  .filter((t) => tools[t]?.group === "apple")
                  .map((t) => (
                    <span className="tool-chip chip-apple" key={t}>
                      {t}
                    </span>
                  ))}
              </span>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
