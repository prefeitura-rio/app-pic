#!/usr/bin/env python3
"""Test script for the policy writer (rls.access_policy sync).

Fetches a client_credentials token from Keycloak and makes HTTP requests to the
data-proxy PostgREST API to test GRANT, REVOKE, and LIST operations on access_policy.

Usage:
    # Grant a permission
    uv run python scripts/test_policy_writer.py grant --cpf 12345678900 --unit-type cras --unit-id CRAS_001

    # Revoke a permission
    uv run python scripts/test_policy_writer.py revoke --cpf 12345678900 --unit-type cras --unit-id CRAS_001

    # List all permissions
    uv run python scripts/test_policy_writer.py list

    # Grant with custom options
    uv run python scripts/test_policy_writer.py grant --cpf 12345678900 --unit-type escola --unit-id ESCOLA_123 --is-admin

    # List permissions for a specific subject (CPF)
    uv run python scripts/test_policy_writer.py list --cpf 12345678900
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx

# Load environment
if os.path.exists("src/config/.env"):
    import dotenv

    dotenv.load_dotenv(dotenv_path="src/config/.env", override=True)

from src.config import env


class PolicyWriterClient:
    """Client for testing the policy writer (rls.access_policy)."""

    def __init__(self):
        self.api_url = env.DATA_PROXY_API_URL
        self.schema = env.DATA_PROXY_SCHEMA
        self.token_url = env.DATA_PROXY_TOKEN_URL
        self.client_id = env.DATA_PROXY_CLIENT_ID
        self.client_secret = env.DATA_PROXY_CLIENT_SECRET
        self.token: str | None = None

    async def get_token(self) -> str:
        """Fetch client_credentials token from Keycloak."""
        if self.token:
            return self.token

        print(f"[*] Fetching token from: {self.token_url}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            response.raise_for_status()
            payload = response.json()
            self.token = payload["access_token"]
            expires_in = payload.get("expires_in", 3600)
            print(f"[OK] Token fetched! (expires in {expires_in}s)\n")
            return self.token

    def _headers(self, token: str) -> dict[str, str]:
        """Build headers for PostgREST request."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Profile": "rls",  # Target the rls schema
        }

    async def grant(
        self,
        cpf: str,
        unit_type: str,
        unit_id: str,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        """GRANT a permission (upsert into rls.access_policy)."""
        token = await self.get_token()

        # `access_policy` has no `schema`/`is_enabled` columns anymore —
        # just subject, is_admin, unit_type, unit_id, metadata (see plan.md
        # section 3.3).
        payload = [
            {
                "subject": cpf,
                "is_admin": is_admin,
                "unit_type": unit_type,
                "unit_id": unit_id,
            }
        ]

        url = f"{self.api_url}/access_policy"
        params = {"on_conflict": "subject,unit_type,unit_id"}

        print("[REQUEST] GRANT Request:")
        print(f"  URL: POST {url}")
        print(f"  Payload: {json.dumps(payload, indent=2)}")
        print()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._headers(token),
                params=params,
            )

            print(f"[RESPONSE] Status: {response.status_code}")
            if response.text:
                try:
                    result = response.json()
                    print(f"  Body: {json.dumps(result, indent=2)}")
                except json.JSONDecodeError:
                    print(f"  Body: {response.text}")
            print()

            response.raise_for_status()
            return {"status": "success", "status_code": response.status_code}

    async def revoke(
        self,
        cpf: str,
        unit_type: str,
        unit_id: str,
    ) -> dict[str, Any]:
        """REVOKE a permission (hard DELETE of the matching row — the table
        no longer has an `is_enabled` column)."""
        token = await self.get_token()

        url = f"{self.api_url}/access_policy"
        params = {
            "subject": f"eq.{cpf}",
            "unit_type": f"eq.{unit_type}",
            "unit_id": f"eq.{unit_id}",
        }

        print("[REQUEST] REVOKE Request:")
        print(f"  URL: DELETE {url}")
        print(f"  Params: {json.dumps(params, indent=2)}")
        print()

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                url,
                headers=self._headers(token),
                params=params,
            )

            print(f"[RESPONSE] Status: {response.status_code}")
            if response.text:
                try:
                    result = response.json()
                    print(f"  Body: {json.dumps(result, indent=2)}")
                except json.JSONDecodeError:
                    print(f"  Body: {response.text}")
            print()

            response.raise_for_status()
            return {"status": "success", "status_code": response.status_code}

    async def list_policies(self, cpf: str | None = None) -> dict[str, Any]:
        """LIST permissions from rls.access_policy."""
        token = await self.get_token()

        url = f"{self.api_url}/access_policy"

        print("[REQUEST] LIST Request:")
        print(f"  URL: GET {url}")
        if cpf:
            print(f"  Filter: schema = {self.schema}, subject = {cpf}")
        else:
            print(f"  Filter: schema = {self.schema}")
        print()

        params = {"schema": f"eq.{self.schema}"}
        if cpf:
            params["subject"] = f"eq.{cpf}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._headers(token),
                params=params,
            )

            print(f"[RESPONSE] Status: {response.status_code}")
            if response.text:
                try:
                    result = response.json()
                    if isinstance(result, list):
                        print(f"  Found {len(result)} policies:")
                        for idx, policy in enumerate(result, 1):
                            print(f"\n  [{idx}] {policy}")
                    else:
                        print(f"  Body: {json.dumps(result, indent=2)}")
                except json.JSONDecodeError:
                    print(f"  Body: {response.text}")
            print()

            response.raise_for_status()
            return {"status": "success", "status_code": response.status_code}


async def main():
    parser = argparse.ArgumentParser(
        description="Test the policy writer (rls.access_policy) via PostgREST",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Grant a permission
  uv run python scripts/test_policy_writer.py grant --cpf 12345678900 --unit-type cras --unit-id CRAS_001

  # Grant as admin
  uv run python scripts/test_policy_writer.py grant --cpf 12345678900 --unit-type escola --unit-id ESCOLA_123 --is-admin

  # Revoke a permission
  uv run python scripts/test_policy_writer.py revoke --cpf 12345678900 --unit-type cras --unit-id CRAS_001

  # List all permissions
  uv run python scripts/test_policy_writer.py list

  # List permissions for a specific subject
  uv run python scripts/test_policy_writer.py list --cpf 12345678900
        """,
    )

    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # GRANT subcommand
    grant_parser = subparsers.add_parser("grant", help="Grant a permission (UPSERT)")
    grant_parser.add_argument(
        "--cpf",
        required=True,
        help="User CPF (11 digits)",
    )
    grant_parser.add_argument(
        "--unit-type",
        required=True,
        help="Unit type (e.g., cras, escola, cre, ap, cas, clinica_familia, equipe_familia)",
    )
    grant_parser.add_argument(
        "--unit-id",
        required=True,
        help="Unit ID (e.g., CRAS_001, ESCOLA_123)",
    )
    grant_parser.add_argument(
        "--is-admin",
        action="store_true",
        help="Mark as admin",
    )

    # REVOKE subcommand
    revoke_parser = subparsers.add_parser(
        "revoke",
        help="Revoke a permission (hard DELETE)",
    )
    revoke_parser.add_argument(
        "--cpf",
        required=True,
        help="User CPF (11 digits)",
    )
    revoke_parser.add_argument(
        "--unit-type",
        required=True,
        help="Unit type (e.g., cras, escola, cre, ap, cas, clinica_familia, equipe_familia)",
    )
    revoke_parser.add_argument(
        "--unit-id",
        required=True,
        help="Unit ID (e.g., CRAS_001, ESCOLA_123)",
    )

    # LIST subcommand
    list_parser = subparsers.add_parser(
        "list",
        help="List all permissions or for a specific subject",
    )
    list_parser.add_argument(
        "--cpf",
        required=False,
        help="Filter by user CPF (optional)",
    )

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    print("[*] Policy Writer Tester\n")
    print(f"  Data-proxy URL: {env.DATA_PROXY_API_URL}")
    print(f"  Schema: {env.DATA_PROXY_SCHEMA}")
    print(f"  Action: {args.action.upper()}\n")

    client = PolicyWriterClient()

    try:
        if args.action == "grant":
            await client.grant(
                cpf=args.cpf,
                unit_type=args.unit_type,
                unit_id=args.unit_id,
                is_admin=args.is_admin,
            )
            print("[OK] Grant successful!")
        elif args.action == "revoke":
            await client.revoke(
                cpf=args.cpf,
                unit_type=args.unit_type,
                unit_id=args.unit_id,
            )
            print("[OK] Revoke successful!")
        elif args.action == "list":
            await client.list_policies(cpf=args.cpf)
            print("[OK] List successful!")
    except httpx.HTTPStatusError as e:
        print(f"[ERROR] HTTP Error: {e.response.status_code}")
        print(f"  Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
