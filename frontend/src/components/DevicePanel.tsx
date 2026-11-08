import { useState } from "react";
import { addDevice, removeDevice, type Device } from "../api";

type Props = {
  devices: Device[];
  onChanged: () => void;
};

/** SQLite stocke les dates en UTC sans suffixe de zone ; on le rajoute avant
 *  conversion, sinon le navigateur les interprète comme locales. */
function formatDate(raw: string): string {
  const parsed = new Date(raw.replace(" ", "T") + "Z");
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function DevicePanel({ devices, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      const err = e as Error;
      if (err.name !== "NotAllowedError" && err.name !== "AbortError") {
        setError(err.message || "Opération impossible.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="devices">
      <h3>Appareils autorisés</h3>

      {devices.map((device) => (
        <div className="device-row" key={device.id}>
          <span className="grow">{device.label ?? "Appareil"}</span>
          <time>{formatDate(device.created_at)}</time>
          <button
            className="link-btn"
            disabled={busy || devices.length <= 1}
            title={
              devices.length <= 1
                ? "Impossible de retirer la dernière passkey"
                : "Retirer cet appareil"
            }
            onClick={() => void run(() => removeDevice(device.id))}
          >
            Retirer
          </button>
        </div>
      ))}

      <div className="device-row">
        <button
          className="ghost-btn"
          disabled={busy}
          onClick={() => void run(() => addDevice("Appareil secondaire"))}
        >
          + Ajouter une passkey
        </button>
      </div>

      {error && <p className="alert">{error}</p>}
    </div>
  );
}
