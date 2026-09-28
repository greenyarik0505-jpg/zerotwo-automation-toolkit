import urllib.parse
from typing import Dict, Any, Optional, Tuple
from curl_cffi.requests import AsyncSession


class ZeroTwoError(Exception):
    pass


class ZeroTwoClient:
    """
    Клиент для взаимодействия с API ZeroTwo (Supabase GoTrue & REST API).
    """

    SUPABASE_URL = "https://db.zerotwo.ai"
    ANON_KEY = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpkYmNldmpicWFveHJ4eHdxd3V4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTgyNDcyMzUsImV4cCI6MjA3MzgyMzIzNX0."
        "UcUJUjMocwijFTtYFKYuTgIODYWc4uxDByu2tI6XGQg"
    )

    @classmethod
    def get_anon_headers(cls) -> dict:
        return {
            "apikey": cls.ANON_KEY,
            "Authorization": f"Bearer {cls.ANON_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @classmethod
    def get_auth_headers(cls, access_token: str) -> dict:
        return {
            "apikey": cls.ANON_KEY,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

    @classmethod
    async def signup(
        cls,
        session: AsyncSession,
        email: str,
        password: str,
        display_name: str = "ZeroTwo User",
    ) -> Dict[str, Any]:
        """
        Регистрирует аккаунт через GoTrue API без капчи.
        """
        url = f"{cls.SUPABASE_URL}/auth/v1/signup"
        payload = {
            "email": email,
            "password": password,
            "data": {
                "full_name": display_name,
                "display_name": display_name,
            },
        }

        resp = await session.post(url, headers=cls.get_anon_headers(), json=payload)
        if resp.status_code not in (200, 201):
            raise ZeroTwoError(f"Signup failed [{resp.status_code}]: {resp.text}")

        data = resp.json()
        return data

    @classmethod
    async def verify_confirmation_link(
        cls,
        session: AsyncSession,
        link: str,
        max_hops: int = 6,
    ) -> Tuple[str, str]:
        """
        Переходит по цепочке редиректов письма подтверждения и извлекает
        access_token и refresh_token из фрагмента или query URL.
        """
        current_url = link.strip().rstrip("]>.)\"'")

        for hop in range(max_hops):
            resp = await session.get(current_url, allow_redirects=False)
            loc = resp.headers.get("Location") or resp.headers.get("location")

            target_check = loc or resp.url
            if target_check and ("access_token=" in target_check or "refresh_token=" in target_check):
                fragment = urllib.parse.urlparse(target_check).fragment
                query = urllib.parse.urlparse(target_check).query

                params = dict(urllib.parse.parse_qsl(fragment))
                if not params or "access_token" not in params:
                    params = dict(urllib.parse.parse_qsl(query))

                access_token = params.get("access_token")
                refresh_token = params.get("refresh_token")

                if access_token and refresh_token:
                    return access_token, refresh_token

            if not loc:
                break

            current_url = loc

        raise ZeroTwoError(f"Tokens not found in confirmation redirect chain for {link}")

    @classmethod
    async def login_with_password(
        cls,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> Dict[str, Any]:
        """
        Авторизация по логину и паролю. Проверяет валидность созданного аккаунта.
        """
        url = f"{cls.SUPABASE_URL}/auth/v1/token?grant_type=password"
        payload = {"email": email, "password": password}

        resp = await session.post(url, headers=cls.get_anon_headers(), json=payload)
        if resp.status_code != 200:
            raise ZeroTwoError(f"Password login failed [{resp.status_code}]: {resp.text}")

        return resp.json()

    @classmethod
    async def complete_onboarding(
        cls,
        session: AsyncSession,
        access_token: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Устанавливает onboarding_completed: true для активации полного функционала ZeroTwo.
        """
        url = f"{cls.SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
        payload = {"onboarding_completed": True}

        resp = await session.patch(
            url,
            headers=cls.get_auth_headers(access_token),
            json=payload,
        )
        if resp.status_code not in (200, 204):
            return {}

        return resp.json() if resp.text else {}

    @classmethod
    async def get_profile(
        cls,
        session: AsyncSession,
        access_token: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Получает профиль пользователя и статус подписки.
        """
        url = f"{cls.SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
        resp = await session.get(url, headers=cls.get_auth_headers(access_token))
        if resp.status_code == 200:
            rows = resp.json()
            return rows[0] if rows else None
        return None
