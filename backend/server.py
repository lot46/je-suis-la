@api.post("/auth/verify-code")
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()

    record = otp_store.get(email)

    if not record:
        raise HTTPException(status_code=400, detail="Code introuvable")

    if datetime.utcnow() > record["expires_at"]:
        del otp_store[email]
        raise HTTPException(status_code=400, detail="Code expiré")

    if code != record["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    # Code valide → suppression immédiate (one-time use)
    del otp_store[email]

    token = generate_token()

    return {
        "token": token
    }
