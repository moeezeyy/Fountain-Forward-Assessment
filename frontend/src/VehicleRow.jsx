import { useState } from "react";
import { api, ApiError } from "./api";

const STATUSES = ["available", "pending", "sold"];

export default function VehicleRow({ vehicle, canEdit, onUpdated, onSessionExpired }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(vehicle);
  const [error, setError] = useState(null);
  const [conflict, setConflict] = useState(null);
  const [saving, setSaving] = useState(false);

  function startEdit() {
    setForm(vehicle);
    setError(null);
    setConflict(null);
    setEditing(true);
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setConflict(null);
    try {
      const updated = await api.updateVehicle(vehicle.id, {
        make: form.make,
        model: form.model,
        year: Number(form.year),
        status: form.status,
        version: vehicle.version,
      });
      onUpdated(updated);
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onSessionExpired();
      } else if (err instanceof ApiError && err.status === 403) {
        setError("You don't have permission to edit this vehicle.");
      } else if (err instanceof ApiError && err.status === 409) {
        setConflict(err.body?.detail?.current_version);
      } else {
        setError("Could not save changes. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleRefresh() {
    const latest = await api.getVehicle(vehicle.id);
    onUpdated(latest);
    setForm(latest);
    setConflict(null);
  }

  if (!editing) {
    return (
      <tr>
        <td>{vehicle.make}</td>
        <td>{vehicle.model}</td>
        <td>{vehicle.year}</td>
        <td>
          <span className={`status-badge status-${vehicle.status}`}>{vehicle.status}</span>
        </td>
        <td>
          {canEdit && (
            <button type="button" onClick={startEdit}>
              Edit
            </button>
          )}
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td colSpan={5}>
        <form className="edit-row" onSubmit={handleSave}>
          <input
            value={form.make}
            onChange={(e) => setForm({ ...form, make: e.target.value })}
            placeholder="Make"
            required
          />
          <input
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
            placeholder="Model"
            required
          />
          <input
            type="number"
            value={form.year}
            onChange={(e) => setForm({ ...form, year: e.target.value })}
            min="1900"
            max="2100"
            required
          />
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button type="submit" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>

          {error && <p className="error-text">{error}</p>}
          {conflict !== null && (
            <div className="conflict-banner">
              <p>
                This vehicle was updated by someone else in the meantime (now at version{" "}
                {conflict}). Your change was not saved. Refresh to see the latest version before
                retrying.
              </p>
              <button type="button" onClick={handleRefresh}>
                Refresh
              </button>
            </div>
          )}
        </form>
      </td>
    </tr>
  );
}
