"""
Secure NASA Earthdata Authentication & Credential Management for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Security Principles:
- Never prints, logs, or transmits unmasked tokens or passwords.
- Strict 0600 file permission enforcement for credential files.
- Supports Bearer Token (~/.config/earthpulse/earthdata.env) and official ASFSession.auth_with_token().
- Supports RFC-standard ~/.netrc fallback.
- Provides unauthenticated public search fallback when credentials are not configured.
"""

import os
import sys
import stat
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

# Ensure workspace-vendored packages are accessible if present
_LOCAL_PACKAGES = Path(__file__).resolve().parent.parent.parent / ".packages"
if _LOCAL_PACKAGES.exists() and str(_LOCAL_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_LOCAL_PACKAGES))

try:
    import asf_search as asf
    _HAS_ASF_SEARCH = True
except ImportError:
    asf = None
    _HAS_ASF_SEARCH = False

import requests

logger = logging.getLogger("EarthPulse.EarthdataAuth")

DEFAULT_TOKEN_FILE = Path.home() / ".config" / "earthpulse" / "earthdata.env"
DEFAULT_NETRC_FILE = Path.home() / ".netrc"


def mask_secret(secret: Optional[str]) -> str:
    """Safely mask sensitive strings for display and logging."""
    if not secret:
        return "[NOT_CONFIGURED]"
    secret_str = str(secret).strip()
    if len(secret_str) <= 8:
        return "****"
    return f"{secret_str[:4]}...{secret_str[-4:]}"


def verify_file_permissions(path: Path) -> Tuple[bool, str]:
    """
    Verify that a credential file is strictly protected (0600 or 0400).
    Group and other permissions must be 0 (no read/write/execute for non-owner).
    """
    if not path.exists():
        return False, f"File does not exist: {path}"
    
    st_mode = path.stat().st_mode
    if (st_mode & 0o077) != 0:
        actual_octal = oct(stat.S_IMODE(st_mode))
        return False, f"Insecure permissions ({actual_octal}): must be 0600 (owner read/write only)"
    
    return True, "Permissions verified (0600/owner-only)"


def _parse_token_from_text(content: str) -> Optional[str]:
    """
    Parse a token from various formats:
    - Raw token string (JWT / Bearer)
    - EARTHDATA_TOKEN=your_token
    - export EARTHDATA_TOKEN="your_token"
    """
    if not content:
        return None
    
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    for line in lines:
        m = re.match(r'^(?:export\s+)?(?:EARTHDATA_TOKEN|NASA_TOKEN|TOKEN)\s*=\s*["\']?([^"\']+)["\']?$', line)
        if m:
            return m.group(1).strip()
        if "=" not in line:
            return line.strip()
    return None


def get_stored_token(token_file: Path = DEFAULT_TOKEN_FILE) -> Optional[str]:
    """
    Retrieve stored NASA Earthdata Bearer token.
    Checks:
    1. Environment variable EARTHDATA_TOKEN
    2. Local file ~/.config/earthpulse/earthdata.env (enforcing 0600)
    3. Workspace file .earthdata-token (enforcing 0600)
    """
    env_token = os.environ.get("EARTHDATA_TOKEN")
    if env_token:
        return env_token.strip()
    
    candidate_paths = [
        token_file,
        Path.home() / ".earthdata-token",
        Path(".earthdata-token"),
    ]
    
    for path in candidate_paths:
        if path.exists():
            valid, _ = verify_file_permissions(path)
            if valid:
                try:
                    raw_text = path.read_text(encoding="utf-8")
                    parsed = _parse_token_from_text(raw_text)
                    if parsed:
                        return parsed
                except Exception as e:
                    logger.warning("Failed to read token file %s: %s", path, e)
    
    return None


def save_token(token: str, path: Path = DEFAULT_TOKEN_FILE) -> Tuple[bool, str]:
    """
    Save Bearer token to local file with strict 0600 permissions.
    """
    if not token or not token.strip():
        return False, "Empty token provided."
    
    try:
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = stat.S_IRUSR | stat.S_IWUSR
        fd = os.open(path, flags, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"EARTHDATA_TOKEN={token.strip()}\n")
        os.chmod(path, mode)
        return True, f"Token successfully stored at {path} with 0600 permissions."
    except Exception as e:
        return False, f"Failed to save token to {path}: {e}"


def get_netrc_credentials(netrc_file: Path = DEFAULT_NETRC_FILE) -> Optional[Dict[str, str]]:
    """
    Safely retrieve credentials for urs.earthdata.nasa.gov from ~/.netrc.
    Enforces 0600 permissions.
    """
    if not netrc_file.exists():
        return None
    
    valid, _ = verify_file_permissions(netrc_file)
    if not valid:
        return None
    
    try:
        import netrc
        n = netrc.netrc(str(netrc_file))
        auth = n.authenticators("urs.earthdata.nasa.gov")
        if auth:
            login, account, password = auth
            return {"login": login, "password": password}
    except Exception as e:
        logger.debug("Could not parse netrc: %s", e)
    return None


def save_netrc_credentials(login: str, password: str, netrc_file: Path = DEFAULT_NETRC_FILE) -> Tuple[bool, str]:
    """
    Save or update urs.earthdata.nasa.gov entry in ~/.netrc with 0600 permissions.
    """
    if not login or not password:
        return False, "Login and password required."
    
    try:
        netrc_file = Path(netrc_file).resolve()
        existing_lines = []
        if netrc_file.exists():
            existing_lines = netrc_file.read_text(encoding="utf-8").splitlines()
        
        new_lines = []
        skip = False
        for line in existing_lines:
            if "machine urs.earthdata.nasa.gov" in line:
                skip = True
                continue
            if skip:
                if line.startswith("machine ") or not line.strip():
                    skip = False
                    new_lines.append(line)
                continue
            new_lines.append(line)
        
        new_entry = (
            f"machine urs.earthdata.nasa.gov\n"
            f"  login {login.strip()}\n"
            f"  password {password.strip()}\n"
        )
        
        final_content = "\n".join([l for l in new_lines if l.strip()]) + ("\n" if new_lines else "") + new_entry
        
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = stat.S_IRUSR | stat.S_IWUSR
        fd = os.open(netrc_file, flags, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(final_content)
        os.chmod(netrc_file, mode)
        return True, f"Saved credentials to {netrc_file} with 0600 permissions."
    except Exception as e:
        return False, f"Failed to write netrc: {e}"


def audit_earthdata_configuration() -> Dict[str, Any]:
    """
    Audit current authentication configuration without leaking sensitive tokens.
    """
    token = get_stored_token()
    token_configured = token is not None
    masked_token = mask_secret(token) if token else None

    netrc_configured = False
    netrc_valid_perms = False
    netrc_user = None
    if DEFAULT_NETRC_FILE.exists():
        netrc_valid_perms, _ = verify_file_permissions(DEFAULT_NETRC_FILE)
        if netrc_valid_perms:
            creds = get_netrc_credentials()
            if creds:
                netrc_configured = True
                netrc_user = creds.get("login")

    return {
        "token_configured": token_configured,
        "token_masked": masked_token,
        "token_file_exists": DEFAULT_TOKEN_FILE.exists(),
        "netrc_configured": netrc_configured,
        "netrc_valid_perms": netrc_valid_perms,
        "netrc_user": netrc_user,
        "has_asf_search": _HAS_ASF_SEARCH,
        "can_search_public": True,
        "can_download": token_configured or netrc_configured,
    }


class EarthdataSessionManager:
    """
    Manages authenticated NASA Earthdata sessions for ASF DAAC and NASA data pools.
    Provides ASFSession for asf_search and requests.Session for raw HTTP streaming.
    """

    @classmethod
    def get_token(cls) -> Optional[str]:
        return get_stored_token()

    @classmethod
    def get_asf_session(cls) -> Optional[Any]:
        if not _HAS_ASF_SEARCH:
            return None

        session = asf.ASFSession()
        token = cls.get_token()

        if token:
            try:
                session.auth_with_token(token)
                return session
            except Exception as e:
                logger.error("Failed to authenticate ASFSession with token: %s", e)

        if DEFAULT_NETRC_FILE.exists():
            valid, _ = verify_file_permissions(DEFAULT_NETRC_FILE)
            if valid:
                try:
                    return session
                except Exception:
                    pass

        return session

    @classmethod
    def get_requests_session(cls) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "EarthPulse-SAR/2026.1 (NASA Space Apps Challenge)",
        })

        token = cls.get_token()
        if token:
            session.headers.update({
                "Authorization": f"Bearer {token}",
            })

        return session

    @classmethod
    def test_authentication(cls) -> Dict[str, Any]:
        audit = audit_earthdata_configuration()
        if not audit["can_download"]:
            return {
                "success": False,
                "authenticated": False,
                "message": "No Earthdata token or valid .netrc found. Public search available, authenticated download unavailable.",
                "audit": audit,
            }

        session = cls.get_asf_session()
        if session is None:
            session = cls.get_requests_session()

        test_url = "https://datapool.asf.alaska.edu/GRD_HD/SD/S1D_IW_GRDH_1SDV_20261031T235517_20261031T235542_005266_00A038_5A0E.zip"
        try:
            resp = session.get(test_url, headers={"Range": "bytes=0-511"}, timeout=15, stream=True)
            if resp.status_code in (200, 206):
                return {
                    "success": True,
                    "authenticated": True,
                    "method": "Bearer Token (ASFSession)" if audit["token_configured"] else ".netrc",
                    "status_code": resp.status_code,
                    "bytes_received": len(resp.content),
                    "message": "NASA Earthdata authentication verified successfully via ASFSession.",
                    "audit": audit,
                }
            elif resp.status_code in (401, 403):
                return {
                    "success": False,
                    "authenticated": False,
                    "status_code": resp.status_code,
                    "message": f"Authentication rejected by NASA Earthdata (HTTP {resp.status_code}). Please verify token validity.",
                    "audit": audit,
                }
            else:
                return {
                    "success": False,
                    "authenticated": False,
                    "status_code": resp.status_code,
                    "message": f"Unexpected response from NASA DAAC: HTTP {resp.status_code}",
                    "audit": audit,
                }
        except Exception as e:
            return {
                "success": False,
                "authenticated": False,
                "error": str(e),
                "message": f"Network error during authentication test: {e}",
                "audit": audit,
            }
