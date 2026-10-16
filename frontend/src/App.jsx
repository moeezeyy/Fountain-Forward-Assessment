import { AuthProvider, useAuth } from "./AuthContext";
import LoginPage from "./LoginPage";
import InventoryPage from "./InventoryPage";
import "./App.css";

function Gate() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="centered-page">
        <p>Loading...</p>
      </div>
    );
  }

  return user ? <InventoryPage /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
