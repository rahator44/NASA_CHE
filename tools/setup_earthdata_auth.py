#!/usr/bin/env python3
"""
CLI Utility: Setup and Verify NASA Earthdata Authentication for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_LOCAL_PACKAGES = PROJECT_ROOT / ".packages"
if _LOCAL_PACKAGES.exists() and str(_LOCAL_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_LOCAL_PACKAGES))

from src.core.earthdata_auth import (
    audit_earthdata_configuration,
    EarthdataSessionManager,
    save_token,
    save_netrc_credentials,
)


def print_status():
    audit = audit_earthdata_configuration()
    print("=" * 60)
    print("EARTH PULSE — NASA EARTHDATA CONFIGURATION STATUS")
    print("=" * 60)
    print(f"Token Configured:    {audit['token_configured']} ({audit.get('token_masked') or 'None'})")
    print(f"Token File Exists:   {audit['token_file_exists']}")
    print(f".netrc Configured:   {audit['netrc_configured']} (Valid 0600 Perms: {audit['netrc_valid_perms']})")
    if audit.get("netrc_user"):
        print(f".netrc User:         {audit['netrc_user']}")
    print(f"asf_search Library:  {audit['has_asf_search']}")
    print(f"Public Search:       {'AVAILABLE' if audit['can_search_public'] else 'UNAVAILABLE'}")
    print(f"Protected Download:  {'READY' if audit['can_download'] else 'CREDENTIALS NEEDED'}")
    print("=" * 60)


def test_auth():
    print("Testing NASA Earthdata authenticated session...")
    res = EarthdataSessionManager.test_authentication()
    print(f"Success:      {res.get('success')}")
    print(f"Auth Status:  {res.get('authenticated')}")
    print(f"Method:       {res.get('method', 'N/A')}")
    print(f"Message:      {res.get('message')}")
    if res.get("bytes_received"):
        print(f"Test Bytes:   {res['bytes_received']} bytes received from NASA DAAC")


def main():
    parser = argparse.ArgumentParser(description="Earth Pulse NASA Earthdata Setup")
    parser.add_argument("--status", action="store_true", help="Print configuration status")
    parser.add_argument("--test", action="store_true", help="Test live authentication")
    parser.add_argument("--set-token", type=str, help="Save an Earthdata Bearer Token securely")
    args = parser.parse_args()

    if args.set_token:
        success, msg = save_token(args.set_token)
        print(msg)
        if success:
            test_auth()
        sys.exit(0 if success else 1)

    if args.test:
        test_auth()
        sys.exit(0)

    print_status()


if __name__ == "__main__":
    main()
