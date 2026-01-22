# Plan « Je suis là » – MVP

## 1. Objectif
Un outil minimaliste de présence choisie :
- Une personne indique « comment elle est » via un petit statut très simple.
- Une ou plusieurs autres personnes peuvent venir consulter ce statut.
- Aucune géolocalisation, aucune surveillance, aucun marketing, aucune notification.

## 2. Parcours utilisateur (MVP)

### 2.1. Création et connexion
- L’utilisateur saisit son e-mail.
- Backend enregistre l’utilisateur (s’il n’existe pas) et génère un code à 6 chiffres à usage unique, avec une durée de validité courte (ex. 15 minutes).
- Le code est retourné dans la réponse (MVP sans envoi d’e-mail réel, pour rester simple).
- L’utilisateur saisit le code sur l’écran de vérification.
- Si le code est correct et valide, le backend renvoie un token de session (UUID stocké côté backend et renvoyé au frontend) et les infos de l’utilisateur.
- Le frontend stocke ce token dans localStorage et l’envoie dans un header custom (`X-Session-Token`) à chaque requête.

### 2.2. Page principale « Je suis là »
- Une fois connecté, l’utilisateur voit une page très simple :
  - Son statut actuel (par exemple : « je vais bien », « journée normale », « pas disponible » ou rien si aucun statut encore).
  - Un bouton pour choisir / changer son statut parmi une liste très courte de statuts prédéfinis.
  - Un texte d’explication sur la philosophie de l’outil (présence choisie, sans tracking, sans pub).
- Pas de notion de « liste d’amis » dans le MVP : on suppose que la page peut être partagée (plus tard) via un lien, mais techniquement, le MVP se limite à un seul compte qui voit son propre statut, et toute personne ayant accès au navigateur peut voir ce statut.

### 2.3. Consultation par une autre personne
- Scénario MVP simplifié :
  - La personne connectée reste connectée dans son navigateur.
  - Une autre personne (partenaire, ami, famille) peut ouvrir la même page sur ce navigateur et voir le statut.
- Évolution future (non incluse dans le MVP, mais prévue dans l’architecture) :
  - Générer un lien public en lecture seule (ex. `/p/{public_id}`) qui affiche le dernier statut de l’utilisateur sans aucune donnée sensible.

## 3. Architecture technique

### 3.1. Backend (FastAPI + MongoDB)
- Base : fichier `server.py` existant, enrichi.
- Collections MongoDB :
  - `users` :
    - `_id` (ObjectId)
    - `email` (str, unique)
    - `created_at` (datetime ISO)
    - `last_login_at` (datetime ISO, optionnel)
  - `login_codes` :
    - `_id` (ObjectId)
    - `user_id` (ObjectId)
    - `code` (str, 6 chiffres)
    - `expires_at` (datetime ISO)
    - `used` (bool)
  - `sessions` :
    - `_id` (ObjectId)
    - `user_id` (ObjectId)
    - `token` (str, UUID)
    - `created_at` (datetime ISO)
  - `statuses` :
    - `_id` (ObjectId)
    - `user_id` (ObjectId)
    - `status_key` (str, une clé parmi la liste prédéfinie)
    - `status_label` (str, texte affiché)
    - `updated_at` (datetime ISO)

- Endpoints API (tous préfixés par `/api` via `api_router`) :
  - `POST /auth/request-code`
    - Input : `{ email: string }`
    - Effet : crée l’utilisateur si besoin, génère un code, le stocke en base, renvoie une réponse comme `{ message: "code_generated", code: "123456" }` (MVP, sans e-mail).
  - `POST /auth/verify-code`
    - Input : `{ email: string, code: string }`
    - Vérifie le code (non utilisé, non expiré, correspond à l’utilisateur).
    - Marque le code comme utilisé, crée une session (token UUID).
    - Renvoie : `{ token, user: { id, email } }`.
  - Middleware ou dépendance `get_current_user`
    - Lit `X-Session-Token`.
    - Vérifie la session en base et récupère l’utilisateur associé.
  - `GET /me/status`
    - Authentifié.
    - Renvoie le dernier statut de l’utilisateur ou `null` si aucun.
  - `POST /me/status`
    - Authentifié.
    - Input : `{ status_key: string }`.
    - Vérifie que `status_key` fait partie des valeurs autorisées, en déduit `status_label`.
    - Met à jour ou crée le statut en base.
    - Renvoie `{ status_key, status_label, updated_at }`.

- Liste des statuts autorisés (backend).
  - `OK` → « Je vais bien »
  - `NORMAL` → « Journée normale »
  - `NOT_AVAILABLE` → « Pas disponible »
  - `NEED_CONTACT` → « Besoin de parler » (optionnel déjà dans le MVP, mais utile)

### 3.2. Frontend (React + Tailwind + shadcn/ui)

#### Écrans principaux

1. **Écran d’accueil / Connexion par e-mail**
   - Champ e-mail + bouton « Recevoir un code ».
   - Après succès, affichage du code renvoyé (MVP) + message « Entrez ce code pour vous connecter ».
   - Zone de saisie du code (6 cases ou un input simple) + bouton « Se connecter ».
   - Design sobre, texte explicatif sur l’absence de surveillance, de géolocalisation, de marketing.

2. **Écran principal « Je suis là »**
   - Affiche :
     - Un titre « Je suis là ».
     - Le statut actuel (ou un message du type « Aucun statut défini pour le moment »).
     - Des boutons pour choisir un statut prédéfini (boutons en pilule, discrets, par exemple en ligne ou en grille).
     - Un petit texte rappelant : « Cet espace n’enregistre que ce que vous choisissez de partager. Aucune géolocalisation, aucune publicité, aucune notification. »

#### Gestion de l’état côté frontend
- Stocker le `token` et l’e-mail dans `localStorage`.
- Au chargement de l’app :
  - Si `token` présent, appeler `GET /me/status`.
  - Sinon, afficher l’écran de connexion.

#### Appels API
- Base URL : `process.env.REACT_APP_BACKEND_URL`.
- Utiliser `axios`.
- Ajouter le header `X-Session-Token` automatiquement (via un petit wrapper axios ou directement dans les appels authentifiés).

#### Data-testid (pour tests)
- Tous les éléments interactifs et informations clés auront un `data-testid`, par ex. :
  - `email-input`, `request-code-button`, `code-display`, `code-input`, `verify-code-button`.
  - `main-status-text`, `status-option-ok`, `status-option-normal`, `status-option-not-available`, `status-option-need-contact`.

## 4. Sécurité & confidentialité (adaptée au MVP)
- Aucune donnée de localisation, aucun tracking analytics.
- Juste e-mail + statut simple.
- Pas d’envoi réel d’e-mails pour le moment (le code est retourné dans la réponse pour simplifier l’usage pendant la phase de test).
- Pas de cookies, seulement un token de session stocké côté client.

## 5. Tests
- Tests manuels via le navigateur + `curl` de base.
- Ensuite, utilisation du testing agent automatisé pour :
  - Vérifier les endpoints `/auth/*` et `/me/status`.
  - Tester le flux complet côté frontend : saisie de l’e-mail → réception du code → connexion → changement de statut.

## 6. Étapes de développement
1. Mettre à jour le backend :
   - Modèles MongoDB et schémas Pydantic.
   - Endpoints d’auth par code + endpoints de statut.
   - Dépendance d’authentification.
2. Créer l’interface React :
   - Écran e-mail + code.
   - Écran principal avec statut.
   - Intégration avec les endpoints.
3. Tests (backend + frontend), corrections, nettoyage.

Ce plan reste volontairement minimaliste pour coller à votre souhait de simplicité et de sobriété.