"""Private, per-user case history backed by Supabase.

This module deliberately uses only the Supabase *anon* key plus a user's
short-lived session token. The database policies in ``supabase/schema.sql``
enforce ownership; never add a service-role key to a Streamlit deployment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str
    access_token: str
    refresh_token: str


class HistoryStore:
    """A small Supabase adapter with no import-time dependency on Supabase."""

    def __init__(self, url: str, anon_key: str) -> None:
        self.url = url
        self.anon_key = anon_key

    @classmethod
    def from_environment(cls) -> "HistoryStore | None":
        url = os.getenv("SUPABASE_URL", "").strip()
        anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
        return cls(url, anon_key) if url and anon_key else None

    def _client(self):
        from supabase import create_client

        return create_client(self.url, self.anon_key)

    def request_email_code(self, email: str) -> None:
        self._client().auth.sign_in_with_otp({"email": email})

    def verify_email_code(self, email: str, code: str) -> AuthenticatedUser:
        response = self._client().auth.verify_otp(
            {"email": email, "token": code, "type": "email"}
        )
        session = response.session
        user = response.user
        if session is None or user is None:
            raise RuntimeError("Supabase did not return an authenticated session.")
        return AuthenticatedUser(
            id=str(user.id),
            email=str(user.email or email),
            access_token=session.access_token,
            refresh_token=session.refresh_token,
        )

    def _user_client(self, user: AuthenticatedUser):
        client = self._client()
        client.auth.set_session(user.access_token, user.refresh_token)
        # Verify the token before using it for a database operation.
        verified = client.auth.get_user(user.access_token).user
        if verified is None or str(verified.id) != user.id:
            raise RuntimeError("Your sign-in session could not be verified. Please sign in again.")
        return client

    def list_cases(self, user: AuthenticatedUser) -> list[dict[str, Any]]:
        response = (
            self._user_client(user)
            .table("cases")
            .select("id,title,scenario,verdict,trace,usage,created_at,updated_at")
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        )
        return response.data or []

    def save_case(
        self,
        user: AuthenticatedUser,
        *,
        case_id: str | None,
        title: str,
        scenario: str,
        verdict: dict[str, Any] | None,
        trace: list[Any],
        usage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        client = self._user_client(user)
        payload = {
            "user_id": user.id,
            "title": title,
            "scenario": scenario,
            "verdict": verdict,
            "trace": trace,
            "usage": usage,
        }
        if case_id:
            response = (
                client.table("cases")
                .update(payload)
                .eq("id", case_id)
                .select()
                .single()
                .execute()
            )
        else:
            response = client.table("cases").insert(payload).select().single().execute()
        return response.data

    def delete_case(self, user: AuthenticatedUser, case_id: str) -> None:
        self._user_client(user).table("cases").delete().eq("id", case_id).execute()
