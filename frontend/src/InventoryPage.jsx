import { useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { api, ApiError } from "./api";
import VehicleRow from "./VehicleRow";

export default function InventoryPage() {
  const { user, logout, handleSessionExpired } = useAuth();
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listVehicles();
      setVehicles(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        handleSessionExpired();
      } else {
        setError("Could not load inventory. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleUpdated(updated) {
    setVehicles((prev) => prev.map((v) => (v.id === updated.id ? updated : v)));
  }

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <strong>{user.email}</strong> &middot; {user.role} &middot; dealership: {user.dealership_id}
        </div>
        <button type="button" onClick={logout}>
          Log out
        </button>
      </header>

      <h1>Vehicle Inventory</h1>

      {loading && <p>Loading...</p>}
      {error && <p className="error-text">{error}</p>}

      {!loading && !error && (
        <table>
          <thead>
            <tr>
              <th>Make</th>
              <th>Model</th>
              <th>Year</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {vehicles.map((v) => (
              <VehicleRow
                key={v.id}
                vehicle={v}
                canEdit={user.role === "admin"}
                onUpdated={handleUpdated}
                onSessionExpired={handleSessionExpired}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
