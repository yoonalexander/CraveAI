import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthPage } from "./components/AuthPage";
import { AuthProvider } from "./context/AuthContext";
import "./index.css";

const route = window.location.pathname.replace(/\/$/, "") || "/";
const authModes = {
  "/login": "login",
  "/register": "register",
  "/forgot-password": "forgot",
  "/reset-password": "reset",
  "/auth/result": "result",
  "/account": "account",
} as const;
const authMode = authModes[route as keyof typeof authModes];

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AuthProvider>
      {authMode ? <AuthPage mode={authMode} /> : <App />}
    </AuthProvider>
  </React.StrictMode>,
);
