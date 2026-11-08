import {
  startAuthentication,
  startRegistration,
  browserSupportsWebAuthn,
} from "@simplewebauthn/browser";

export type Agent = {
  id: string;
  name: string;
  callsign: string;
  role: string;
  tagline: string;
  accent: string;
  tools: string[];
};

export type AuthStatus = {
  configured: boolean;
  registration_open: boolean;
  rp_id: string;
};

export type Device = {
  id: string;
  label: string | null;
  created_at: string;
};

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* réponse non JSON : on garde le message par défaut */
    }
    throw new ApiError(detail);
  }
  return res.json() as Promise<T>;
}

// --- Authentification ----------------------------------------------------

export const supportsPasskeys = browserSupportsWebAuthn;

export const getAuthStatus = () => request<AuthStatus>("/api/auth/status");

export const getMe = () =>
  request<{ user_id: string; devices: Device[]; model: string }>("/api/auth/me");

export const logout = () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });

export async function registerPasskey(label?: string): Promise<void> {
  const options = await request<Record<string, unknown>>(
    "/api/auth/register/begin",
    { method: "POST" },
  );
  const credential = await startRegistration({ optionsJSON: options as never });
  await request("/api/auth/register/finish", {
    method: "POST",
    body: JSON.stringify({ credential, label }),
  });
}

export async function loginWithPasskey(): Promise<void> {
  const options = await request<Record<string, unknown>>("/api/auth/login/begin", {
    method: "POST",
  });
  const credential = await startAuthentication({ optionsJSON: options as never });
  await request("/api/auth/login/finish", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });
}

export async function addDevice(label?: string): Promise<void> {
  const options = await request<Record<string, unknown>>("/api/auth/devices/begin", {
    method: "POST",
  });
  const credential = await startRegistration({ optionsJSON: options as never });
  await request("/api/auth/register/finish", {
    method: "POST",
    body: JSON.stringify({ credential, label }),
  });
}

export const removeDevice = (id: string) =>
  request<{ ok: boolean }>(`/api/auth/devices/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

// --- Agents --------------------------------------------------------------

export const getAgents = () => request<{ agents: Agent[] }>("/api/agents");

export const resetAgent = (agentId: string) =>
  request<{ ok: boolean }>(`/api/agents/${agentId}/reset`, { method: "POST" });

// --- Conversation en streaming ------------------------------------------

export type StreamHandlers = {
  onText: (chunk: string) => void;
  onThinking: () => void;
  onTool: (name: string) => void;
  onDone: (info: Record<string, unknown>) => void;
  onError: (message: string) => void;
};

/**
 * Envoie un message à un agent et consomme la réponse en Server-Sent Events.
 *
 * On passe par `fetch` et non `EventSource` : EventSource est limité au GET,
 * ce qui obligerait à faire transiter le prompt dans l'URL. Il faut donc
 * découper le flux SSE à la main — c'est le rôle du tampon ci-dessous, car
 * rien ne garantit qu'un chunk réseau contienne un évènement entier.
 */
export async function sendMessage(
  agentId: string,
  prompt: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/agents/${agentId}/chat`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  });

  if (!res.ok || !res.body) {
    let detail = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignoré */
    }
    handlers.onError(detail);
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;

    // Les évènements SSE sont séparés par une ligne vide. Tout résidu reste
    // dans le tampon jusqu'à l'arrivée du reste.
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      dispatch(raw, handlers);
    }
  }
}

function dispatch(raw: string, handlers: StreamHandlers): void {
  let event = "message";
  let data = "";

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }

  switch (event) {
    case "text":
      handlers.onText(String(payload.text ?? ""));
      break;
    case "thinking":
      handlers.onThinking();
      break;
    case "tool":
      handlers.onTool(String(payload.name ?? "outil"));
      break;
    case "done":
      handlers.onDone(payload);
      break;
    case "error":
      handlers.onError(String(payload.message ?? "Erreur inconnue"));
      break;
  }
}
