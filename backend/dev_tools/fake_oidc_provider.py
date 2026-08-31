"""Minimal fake OIDC provider for local testing only. Not part of the shipped app."""
import time
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwk, jwt as jose_jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import uvicorn
import base64

app = FastAPI()

# Generate a throwaway RSA keypair for signing fake ID tokens
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_numbers = _private_key.public_key().public_numbers()


def _b64url_uint(n):
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


KID = "fake-key-1"
PRIVATE_PEM = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "kid": KID,
            "use": "sig",
            "alg": "RS256",
            "n": _b64url_uint(_public_numbers.n),
            "e": _b64url_uint(_public_numbers.e),
        }
    ]
}

ISSUER = "http://127.0.0.1:9999"
ISSUED_CODES = {}  # code -> claims to embed


@app.get("/.well-known/openid-configuration")
def discovery():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
    }


@app.get("/jwks")
def jwks():
    return JWKS


@app.get("/authorize")
def authorize(request: Request):
    # Simulate a user who is already logged in at the IdP - auto-approve and
    # redirect straight back with a fake authorization code.
    redirect_uri = request.query_params["redirect_uri"]
    state = request.query_params["state"]
    code = f"fakecode-{int(time.time()*1000)}"
    ISSUED_CODES[code] = {"email": "jane.doe@acme-corp.example"}
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}")


@app.post("/token")
async def token(request: Request):
    form = await request.form()
    code = form["code"]
    client_id = form["client_id"]
    claims_extra = ISSUED_CODES.pop(code, {"email": "unknown@example.com"})

    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": client_id,
        "sub": "fake-sub-123",
        "iat": now,
        "exp": now + 300,
        **claims_extra,
    }
    id_token = jose_jwt.encode(claims, PRIVATE_PEM, algorithm="RS256", headers={"kid": KID})
    return JSONResponse({"access_token": "fake-access-token", "id_token": id_token, "token_type": "Bearer"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="warning")
