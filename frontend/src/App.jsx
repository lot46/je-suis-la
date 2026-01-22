import React, { useEffect, useState } from "react";
import axios from "axios";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

const STATUS_OPTIONS = [
  { key: "OK", label: "Je suis là" },
  { key: "NEED_CONTACT", label: "Aujourd'hui, c'est différent" },
];

function App() {
  const [step, setStep] = useState("EMAIL");
  const [email, setEmail] = useState("");
  const [generatedCode, setGeneratedCode] = useState("");
  const [inputCode, setInputCode] = useState("");
  const [token, setToken] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const storedToken = window.localStorage.getItem("jsuisla_token");
    const storedEmail = window.localStorage.getItem("jsuisla_email");
    if (storedToken && storedEmail) {
      setToken(storedToken);
      setEmail(storedEmail);
      setStep("MAIN");
      fetchStatus(storedToken);
    }
  }, []);

  const fetchStatus = async (sessionToken) => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_BASE}/api/me/status`, {
        headers: {
          "X-Session-Token": sessionToken,
        },
      });
      setStatus(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleRequestCode = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setLoading(true);
      const res = await axios.post(`${API_BASE}/api/auth/request-code`, { email });
      setGeneratedCode(res.data.code);
      setStep("CODE");
    } catch (err) {
      console.error(err);
      setError("Impossible de générer un code. Merci de réessayer.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setLoading(true);
      const res = await axios.post(`${API_BASE}/api/auth/verify-code`, {
        email,
        code: inputCode,
      });
      const sessionToken = res.data.token;
      setToken(sessionToken);
      window.localStorage.setItem("jsuisla_token", sessionToken);
      window.localStorage.setItem("jsuisla_email", email);
      setStep("MAIN");
      fetchStatus(sessionToken);
    } catch (err) {
      console.error(err);
      setError("Code invalide ou expiré.");
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (statusKey) => {
    if (!token) return;
    setError("");
    try {
      setLoading(true);
      const res = await axios.post(
        `${API_BASE}/api/me/status`,
        { status_key: statusKey },
        {
          headers: {
            "X-Session-Token": token,
          },
        },
      );
      setStatus(res.data);
    } catch (err) {
      console.error(err);
      setError("Impossible de mettre à jour le statut.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    window.localStorage.removeItem("jsuisla_token");
    window.localStorage.removeItem("jsuisla_email");
    setToken(null);
    setStatus(null);
    setEmail("");
    setGeneratedCode("");
    setInputCode("");
    setStep("EMAIL");
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-50 flex flex-col">
      <header className="border-b border-neutral-800 bg-neutral-950/80 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight" data-testid="app-title">
              Je suis là
            </h1>
            <p
              className="text-sm text-neutral-400 mt-1 max-w-xl"
              data-testid="app-subtitle"
            >
              Un espace de présence choisie. Sans surveillance, sans géolocalisation,
              sans marketing, sans notifications.
            </p>
          </div>
          {token && (
            <button
              onClick={handleLogout}
              className="text-xs px-3 py-1 rounded-full border border-neutral-700 text-neutral-300 hover:bg-neutral-800"
              data-testid="logout-button"
            >
              Se déconnecter
            </button>
          )}
        </div>
      </header>

      <main className="flex-1">
        <div className="max-w-3xl mx-auto px-4 py-8">
          {step === "EMAIL" && (
            <Card data-testid="email-step-card" className="bg-neutral-900/70 border-neutral-800">
              <CardHeader>
                <CardTitle className="text-lg font-medium">Connexion par e-mail</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-neutral-400">
                  Entrez votre adresse e-mail. Nous générons un code de connexion à usage
                  unique. Pas de mot de passe à retenir.
                </p>
                <form onSubmit={handleRequestCode} className="space-y-3">
                  <label className="block text-sm font-medium text-neutral-200">
                    E-mail
                    <Input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="mt-1 bg-neutral-900 border-neutral-700 focus-visible:ring-neutral-400"
                      placeholder="vous@example.org"
                      data-testid="email-input"
                    />
                  </label>
                  {error && (
                    <p
                      className="text-sm text-red-400"
                      data-testid="email-error-message"
                    >
                      {error}
                    </p>
                  )}
                  <Button
                    type="submit"
                    disabled={loading}
                    className="w-full rounded-full bg-neutral-100 text-neutral-900 hover:bg-neutral-300"
                    data-testid="request-code-button"
                  >
                    {loading ? "Envoi en cours…" : "Recevoir un code"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}

          {step === "CODE" && (
            <Card data-testid="code-step-card" className="bg-neutral-900/70 border-neutral-800">
              <CardHeader>
                <CardTitle className="text-lg font-medium">Entrez votre code</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-neutral-400">
                  Pour cette première version, le code est affiché ici directement. À
                  terme, il pourra être envoyé par e-mail.
                </p>
                <div className="flex items-center justify-between gap-4 text-sm">
                  <span className="text-neutral-400">Votre code de connexion :</span>
                  <Badge
                    variant="outline"
                    className="text-lg tracking-[0.3em] px-4 py-2 bg-neutral-950/60 border-neutral-600"
                    data-testid="code-display"
                  >
                    {generatedCode || "------"}
                  </Badge>
                </div>
                <form onSubmit={handleVerifyCode} className="space-y-3">
                  <label className="block text-sm font-medium text-neutral-200">
                    Saisissez le code
                    <Input
                      type="text"
                      inputMode="numeric"
                      maxLength={6}
                      value={inputCode}
                      onChange={(e) => setInputCode(e.target.value.replace(/[^0-9]/g, ""))}
                      className="mt-1 bg-neutral-900 border-neutral-700 focus-visible:ring-neutral-400 tracking-[0.3em] text-center text-lg"
                      placeholder="______"
                      data-testid="code-input"
                    />
                  </label>
                  {error && (
                    <p
                      className="text-sm text-red-400"
                      data-testid="code-error-message"
                    >
                      {error}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="rounded-full border-neutral-700 text-neutral-200 hover:bg-neutral-800"
                      onClick={() => setStep("EMAIL")}
                      data-testid="back-to-email-button"
                    >
                      Changer d'e-mail
                    </Button>
                    <Button
                      type="submit"
                      disabled={loading || !inputCode}
                      className="flex-1 rounded-full bg-neutral-100 text-neutral-900 hover:bg-neutral-300"
                      data-testid="verify-code-button"
                    >
                      {loading ? "Vérification…" : "Se connecter"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          {step === "MAIN" && (
            <Card data-testid="main-view-card" className="bg-neutral-900/70 border-neutral-800">
              <CardHeader>
                <CardTitle className="text-lg font-medium">Je suis là</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <section className="space-y-2">
                  <h2
                    className="text-sm font-semibold uppercase tracking-[0.18em] text-neutral-400"
                    data-testid="current-status-heading"
                  >
                    Statut actuel
                  </h2>
                  <p
                    className="text-base text-neutral-100"
                    data-testid="main-status-text"
                  >
                    {loading
                      ? "Chargement…"
                      : status
                      ? status.status_label
                      : "Aucun statut défini pour le moment."}
                  </p>
                  {status && status.updated_at && (
                    <p
                      className="text-xs text-neutral-500 mt-1"
                      data-testid="status-updated-at-text"
                    >
                      Mis à jour le {new Date(status.updated_at).toLocaleString()}
                    </p>
                  )}
                </section>

                <section className="space-y-3">
                  <h2
                    className="text-sm font-semibold uppercase tracking-[0.18em] text-neutral-400"
                    data-testid="choose-status-heading"
                  >
                    Choisir un statut
                  </h2>
                  <div className="flex flex-wrap gap-2">
                    {STATUS_OPTIONS.map((option) => {
                      const isActive = status && status.status_key === option.key;
                      return (
                        <button
                          key={option.key}
                          type="button"
                          onClick={() => handleStatusChange(option.key)}
                          disabled={loading}
                          className={`px-4 py-2 rounded-full border text-sm transition-colors duration-150
                            ${
                              isActive
                                ? "bg-neutral-100 text-neutral-900 border-neutral-100"
                                : "bg-neutral-950/60 text-neutral-100 border-neutral-700 hover:bg-neutral-800"
                            }`}
                          data-testid={`status-option-${option.key.toLowerCase()}`}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                  {error && (
                    <p
                      className="text-sm text-red-400"
                      data-testid="status-error-message"
                    >
                      {error}
                    </p>
                  )}
                </section>

                <section className="pt-4 border-t border-dashed border-neutral-800 space-y-2">
                  <h2
                    className="text-sm font-semibold uppercase tracking-[0.18em] text-neutral-400"
                    data-testid="philosophy-heading"
                  >
                    Philosophie
                  </h2>
                  <p
                    className="text-sm text-neutral-400 leading-relaxed max-w-2xl"
                    data-testid="philosophy-text"
                  >
                    Cet outil ne suit pas vos déplacements, ne collecte pas de données
                    marketing et ne vous enverra aucune notification. Il enregistre
                    seulement ce que vous choisissez d'indiquer ici, pour que les
                    personnes importantes pour vous puissent sentir votre présence, à
                    votre rythme.
                  </p>
                </section>
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
