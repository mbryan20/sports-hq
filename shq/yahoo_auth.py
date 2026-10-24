"""Exchange a one-time Yahoo code (from the redirect_uri=oob consent page) for a refresh token and
store it encrypted in state/yahoo_token.enc. Run by the 'Yahoo re-auth' workflow."""
import sys

from .yahoo import TOKEN_FILE, save_refresh_token, token_request


def main(code):
    tok = token_request(grant_type="authorization_code", code=code.strip())
    if not save_refresh_token(tok["refresh_token"]):
        sys.exit("TOKEN_KEY secret is missing; cannot store the token.")
    # prove the stored token refreshes
    token_request(grant_type="refresh_token", refresh_token=tok["refresh_token"])
    print(f"Stored new Yahoo refresh token in {TOKEN_FILE.name}; refresh verified.")


if __name__ == "__main__":
    main(sys.argv[1])
