import React from "react";
import App from "./App.jsx";

// Simple bridge so the CRA entry point continues to import App from this file
// while the real implementation lives in App.jsx (with JSX and shadcn styling).

export default function AppWrapper() {
  return <App />;
}
