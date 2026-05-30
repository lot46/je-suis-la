/*
  # Initial Schema for Je suis là

  1. Tables
    - `otp_codes`: One-time password codes for email authentication
      - `email` (text, primary key)
      - `code` (text, 6-digit code)
      - `expires_at` (timestamptz)
      - `last_sent_at` (timestamptz)
      - `used` (boolean)

    - `sessions`: User sessions
      - `token` (uuid, primary key)
      - `email` (text)
      - `created_at` (timestamptz)
      - `expires_at` (timestamptz)

    - `status`: User status
      - `email` (text, primary key)
      - `status_key` (text)
      - `status_label` (text)
      - `updated_at` (timestamptz)

  2. Security
    - Enable RLS on all tables
    - Public access for MVP (can be restricted later)
*/

-- OTP codes table
CREATE TABLE IF NOT EXISTS otp_codes (
    email TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_sent_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT FALSE
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    token UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Status table
CREATE TABLE IF NOT EXISTS status (
    email TEXT PRIMARY KEY,
    status_key TEXT NOT NULL,
    status_label TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE otp_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE status ENABLE ROW LEVEL SECURITY;

-- Public policies for MVP (allow all operations)
CREATE POLICY "Allow all on otp_codes" ON otp_codes FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on sessions" ON sessions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on status" ON status FOR ALL USING (true) WITH CHECK (true);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_email ON sessions(email);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
