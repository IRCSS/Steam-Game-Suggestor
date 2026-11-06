import { useEffect, useState } from "react";
import { ApiError, api, type SettingsView } from "../api/client";

interface Props {
  onClose: () => void;
  onSaved: () => void;
  notify: (message: string) => void;
}

interface Draft {
  dataDir: string;
  exportDir: string;
  floor: string;
  offline: boolean;
  rpm: string;
  llmProvider: "claude_code" | "none" | "openai" | "anthropic";
  llmModel: string;
  cliPath: string;
  budget: string;
  timeout: string;
  salary: string;
  currency: string;
  rate: string;
  team: string;
  cut: string;
  steamKey: string; // "" = unchanged
  llmKey: string;
}

const toDraft = (s: SettingsView): Draft => ({
  dataDir: s.data_dir,
  exportDir: s.export_dir,
  floor: String(s.qualification_min_revenue_usd),
  offline: s.offline_mode,
  rpm: String(s.steam_store_requests_per_minute),
  llmProvider: s.llm_provider,
  llmModel: s.llm_model,
  cliPath: s.claude_cli_path,
  budget: String(s.llm_max_budget_usd),
  timeout: String(s.llm_timeout_minutes),
  salary: String(s.salary_per_person_year),
  currency: s.salary_currency,
  rate: String(s.usd_per_salary_unit),
  team: String(s.comparison_team_size),
  cut: String(s.platform_cut_percent),
  steamKey: "",
  llmKey: "",
});

/** Global settings (gear icon). Saved to settings.json next to the app. */
export function SettingsDialog({ onClose, onSaved, notify }: Props) {
  const [view, setView] = useState<SettingsView | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setView(s);
        setDraft(toDraft(s));
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load settings."));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setError("");
    try {
      const saved = await api.saveSettings({
        data_dir: draft.dataDir,
        export_dir: draft.exportDir,
        qualification_min_revenue_usd: Number(draft.floor) || 0,
        offline_mode: draft.offline,
        steam_store_requests_per_minute: Number(draft.rpm) || 35,
        llm_provider: draft.llmProvider,
        llm_model: draft.llmModel,
        claude_cli_path: draft.cliPath,
        llm_max_budget_usd: Number(draft.budget) || 2,
        llm_timeout_minutes: Number(draft.timeout) || 15,
        salary_per_person_year: Number(draft.salary) || 50000,
        salary_currency: draft.currency || "EUR",
        usd_per_salary_unit: Number(draft.rate) || 1,
        comparison_team_size: Number(draft.team) || 3,
        platform_cut_percent: Number(draft.cut) || 0,
        steam_api_key: draft.steamKey ? draft.steamKey : null,
        llm_api_key: draft.llmKey ? draft.llmKey : null,
      });
      setView(saved);
      setDraft(toDraft(saved));
      notify("Settings saved.");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  };

  const openFolder = (target: "data" | "export" | "app") =>
    api.openFolder(target).catch(() => notify("Could not open the folder."));

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="panel settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
        <div className="sidebar-heading">
          <h2 id="settingsTitle">Settings</h2>
          <button className="ghost-button" type="button" onClick={onClose} aria-label="Close settings">
            ✕
          </button>
        </div>
        {error && <p className="settings-warning" role="alert">{error}</p>}
        {view?.warning && <p className="settings-warning">{view.warning}</p>}
        {!draft || !view ? (
          <p className="settings-help">Loading…</p>
        ) : (
          <>
            <section className="settings-section">
              <h3 className="section-title">Data &amp; files</h3>
              <label className="settings-field">
                <span className="input-caption">Data folder (game catalog, Studies, caches, logs)</span>
                <input id="settingsDataDir" type="text" value={draft.dataDir} onChange={(e) => set("dataDir", e.target.value)} />
              </label>
              <p className="settings-help">
                Now: <code>{view.data_dir_resolved}</code>{" "}
                <button className="link-button" type="button" onClick={() => openFolder("data")}>
                  Open
                </button>
                <br />
                Relative paths are next to the app. Default: <code>data</code>. Changing it starts
                using that folder as-is (existing Studies are not moved).
              </p>
              <label className="settings-field">
                <span className="input-caption">JPG export folder</span>
                <input id="settingsExportDir" type="text" value={draft.exportDir} onChange={(e) => set("exportDir", e.target.value)} />
              </label>
              <p className="settings-help">
                Now: <code>{view.export_dir_resolved}</code>{" "}
                <button className="link-button" type="button" onClick={() => openFolder("export")}>
                  Open
                </button>
              </p>
              <p className="settings-help">
                Settings file: <code>{view.settings_file}</code>
              </p>
            </section>

            <section className="settings-section">
              <h3 className="section-title">Catalog</h3>
              <label className="settings-field">
                <span className="input-caption">Qualification floor (estimated gross revenue, USD)</span>
                <input id="settingsFloor" type="number" min={0} step={10000} value={draft.floor} onChange={(e) => set("floor", e.target.value)} />
              </label>
              <label className="settings-check">
                <input type="checkbox" checked={draft.offline} onChange={(e) => set("offline", e.target.checked)} />
                Offline mode (no Steam requests at all)
              </label>
              {view.offline_forced && (
                <p className="settings-warning" data-testid="offline-forced">
                  Offline mode is forced on by the STEAM_STUDY_OFFLINE environment variable.
                </p>
              )}
            </section>

            <section className="settings-section">
              <h3 className="section-title">Steam requests</h3>
              <p className="settings-help">
                Data updates (new games, refreshes, languages) are started from the Data tab.
              </p>
              <label className="settings-field">
                <span className="input-caption">Steam store requests per minute (polite limit)</span>
                <input type="number" min={1} max={120} value={draft.rpm} onChange={(e) => set("rpm", e.target.value)} />
              </label>
            </section>

            <section className="settings-section">
              <h3 className="section-title">LLM research</h3>
              <div className="input-pair">
                <label className="settings-field">
                  <span className="input-caption">Research with</span>
                  <select
                    id="settingsLlmProvider"
                    value={draft.llmProvider === "claude_code" ? "claude_code" : "none"}
                    onChange={(e) => set("llmProvider", e.target.value as Draft["llmProvider"])}
                  >
                    <option value="claude_code">Claude Code CLI on this PC</option>
                    <option value="none">Off</option>
                  </select>
                </label>
                <label className="settings-field">
                  <span className="input-caption">Model (empty = Claude Code default)</span>
                  <input type="text" placeholder="e.g. sonnet" value={draft.llmModel} onChange={(e) => set("llmModel", e.target.value)} />
                </label>
              </div>
              <p className="settings-help" data-testid="claude-cli-status">
                {view.claude_cli_detected ? (
                  <>Claude Code found: <code>{view.claude_cli_detected}</code></>
                ) : (
                  <span className="settings-warning">Claude Code CLI not found on this PC - install it or set its path below.</span>
                )}
              </p>
              <label className="settings-field">
                <span className="input-caption">Claude Code path (empty = detect automatically)</span>
                <input type="text" value={draft.cliPath} onChange={(e) => set("cliPath", e.target.value)} />
              </label>
              <div className="input-pair">
                <label className="settings-field">
                  <span className="input-caption">Max spend per research (USD)</span>
                  <input type="number" min={0.1} step={0.5} value={draft.budget} onChange={(e) => set("budget", e.target.value)} />
                </label>
                <label className="settings-field">
                  <span className="input-caption">Time limit (minutes)</span>
                  <input type="number" min={2} value={draft.timeout} onChange={(e) => set("timeout", e.target.value)} />
                </label>
              </div>
            </section>

            <section className="settings-section">
              <h3 className="section-title">Cost model (research)</h3>
              <p className="settings-help">
                Cost = people × years × salary. Break-even = cost ÷ (1 − platform cut), compared with
                the game's USD revenue estimate.
              </p>
              <div className="input-pair">
                <label className="settings-field">
                  <span className="input-caption">Salary per person-year</span>
                  <input id="settingsSalary" type="number" min={1} step={1000} value={draft.salary} onChange={(e) => set("salary", e.target.value)} />
                </label>
                <label className="settings-field">
                  <span className="input-caption">Currency</span>
                  <input type="text" maxLength={8} value={draft.currency} onChange={(e) => set("currency", e.target.value)} />
                </label>
              </div>
              <div className="input-pair">
                <label className="settings-field">
                  <span className="input-caption">USD per 1 {draft.currency || "unit"}</span>
                  <input type="number" min={0.01} step={0.01} value={draft.rate} onChange={(e) => set("rate", e.target.value)} />
                </label>
                <label className="settings-field">
                  <span className="input-caption">Comparison team size</span>
                  <input type="number" min={1} value={draft.team} onChange={(e) => set("team", e.target.value)} />
                </label>
              </div>
              <label className="settings-field narrow">
                <span className="input-caption">Platform cut (%)</span>
                <input type="number" min={0} max={99} value={draft.cut} onChange={(e) => set("cut", e.target.value)} />
              </label>
            </section>

            <section className="settings-section">
              <h3 className="section-title">Steam Web API key</h3>
              <label className="settings-field">
                <span className="input-caption">
                  {view.steam_api_key_set ? "Set" : "Not set"} - needed to add new games; free at
                  steamcommunity.com/dev/apikey
                </span>
                <input type="password" autoComplete="off" placeholder={view.steam_api_key_set ? "•••••• (unchanged)" : ""} value={draft.steamKey} onChange={(e) => set("steamKey", e.target.value)} />
              </label>
              <p className="settings-warning">
                The key is stored in plain text in settings.json. On a shared drive, everyone with
                access to that folder can read it.
              </p>
            </section>

            <div className="button-stack settings-actions">
              <button id="saveSettingsButton" className="primary-button" type="button" disabled={saving} onClick={save}>
                {saving ? "Saving…" : "Save settings"}
              </button>
              <button className="secondary-button" type="button" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
