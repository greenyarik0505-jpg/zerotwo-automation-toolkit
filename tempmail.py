import asyncio
import random
import re
import string
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from curl_cffi.requests import AsyncSession


class TempMailError(Exception):
    pass


import quopri

def extract_confirmation_link(content: str) -> Optional[str]:
    """
    Универсальное извлечение ссылки активации ZeroTwo из тела письма (text или html).
    Автоматически декодирует Quoted-Printable (разрывы строк soft break).
    """
    if "=3D" in content or "=\r\n" in content or "=\n" in content:
        try:
            content = quopri.decodestring(content.encode("utf-8", errors="ignore")).decode("utf-8", errors="ignore")
        except Exception:
            pass

    def clean(u: str) -> str:
        return u.rstrip("]>.)\"'").strip()

    # 1. Sendgrid click tracking link
    sendgrid_matches = re.findall(r"https://[a-zA-Z0-9.\-_]*sendgrid\.net/ls/click\?[^\s\"'<>\[\]]+", content)
    if sendgrid_matches:
        return clean(sendgrid_matches[0])

    # 2. Прямая ссылка verify от db.zerotwo.ai
    direct_matches = re.findall(r"https://db\.zerotwo\.ai/auth/v1/verify\?[^\s\"'<>\[\]]+", content)
    if direct_matches:
        return clean(direct_matches[0])

    # 3. Любая ссылка подтверждения с token=
    generic_matches = re.findall(r"https://[^\s\"'<>\[\]]*(?:verify|confirm)[^\s\"'<>\[\]]*token=[^\s\"'<>\[\]]+", content)
    if generic_matches:
        return clean(generic_matches[0])

    return None


class BaseTempMailProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def create_inbox(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Создает почтовый ящик.
        Возвращает dict с полями: {"email": str, "password": str, ...auth_data}
        """
        pass

    @abstractmethod
    async def wait_for_confirmation_link(
        self,
        session: AsyncSession,
        inbox_data: Dict[str, Any],
        timeout: int = 60,
        interval: int = 3,
    ) -> str:
        """
        Ожидает письмо и возвращает ссылку подтверждения.
        """
        pass


# =========================================================================
# 1. Провайдер Mail.tm
# =========================================================================
class MailTmProvider(BaseTempMailProvider):
    name = "mail_tm"
    API_BASE = "https://api.mail.tm"
    HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

    async def create_inbox(self, session: AsyncSession) -> Dict[str, Any]:
        resp = await session.get(f"{self.API_BASE}/domains", headers=self.HEADERS)
        if resp.status_code != 200:
            raise TempMailError(f"Mail.tm domains error [{resp.status_code}]")

        data = resp.json()
        members = data if isinstance(data, list) else data.get("hydra:member", [])
        active_domains = [d["domain"] for d in members if d.get("isActive", True)]
        if not active_domains:
            raise TempMailError("Mail.tm: no active domains")

        domain = random.choice(active_domains)
        rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"zt_{rnd}@{domain}"
        pwd = "P@" + "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "!"

        c_resp = await session.post(
            f"{self.API_BASE}/accounts",
            headers=self.HEADERS,
            json={"address": email, "password": pwd},
        )
        if c_resp.status_code not in (200, 201):
            raise TempMailError(f"Mail.tm account creation failed: {c_resp.status_code}")

        t_resp = await session.post(
            f"{self.API_BASE}/token",
            headers=self.HEADERS,
            json={"address": email, "password": pwd},
        )
        if t_resp.status_code != 200:
            raise TempMailError(f"Mail.tm token failed: {t_resp.status_code}")

        token = t_resp.json().get("token")
        return {
            "provider": self.name,
            "email": email,
            "password": pwd,
            "token": token,
        }

    async def wait_for_confirmation_link(
        self,
        session: AsyncSession,
        inbox_data: Dict[str, Any],
        timeout: int = 60,
        interval: int = 3,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {inbox_data['token']}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            resp = await session.get(f"{self.API_BASE}/messages", headers=headers)
            if resp.status_code == 200:
                msgs = resp.json()
                items = msgs if isinstance(msgs, list) else msgs.get("hydra:member", [])
                for m in items:
                    subj = m.get("subject", "").lower()
                    if "zerotwo" in subj or "confirm" in subj or "magic link" in subj:
                        msg_id = m.get("id")
                        d_resp = await session.get(f"{self.API_BASE}/messages/{msg_id}", headers=headers)
                        if d_resp.status_code == 200:
                            det = d_resp.json()
                            content = (det.get("text") or "") + "\n" + str(det.get("html") or "")
                            link = extract_confirmation_link(content)
                            if link:
                                return link
            await asyncio.sleep(interval)
        raise TempMailError(f"Mail.tm: таймаут ожидания письма для {inbox_data['email']}")


# =========================================================================
# 2. Провайдер TempMail.lol (v2 REST API)
# =========================================================================
class TempMailLolProvider(BaseTempMailProvider):
    name = "tempmail_lol"
    API_BASE = "https://api.tempmail.lol/v2"

    async def create_inbox(self, session: AsyncSession) -> Dict[str, Any]:
        resp = await session.post(f"{self.API_BASE}/inbox/create")
        if resp.status_code not in (200, 201):
            raise TempMailError(f"TempMail.lol create error [{resp.status_code}]")

        data = resp.json()
        email = data.get("address")
        token = data.get("token")
        if not email or not token:
            raise TempMailError("TempMail.lol: invalid response")

        return {
            "provider": self.name,
            "email": email,
            "password": "N/A",
            "token": token,
        }

    async def wait_for_confirmation_link(
        self,
        session: AsyncSession,
        inbox_data: Dict[str, Any],
        timeout: int = 60,
        interval: int = 3,
    ) -> str:
        token = inbox_data["token"]
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            resp = await session.get(f"{self.API_BASE}/inbox?token={token}")
            if resp.status_code == 200:
                data = resp.json()
                emails = data.get("emails", [])
                for em in emails:
                    subj = (em.get("subject") or "").lower()
                    if "zerotwo" in subj or "confirm" in subj or "magic link" in subj:
                        body = (em.get("body") or "") + "\n" + (em.get("html") or "")
                        link = extract_confirmation_link(body)
                        if link:
                            return link
            await asyncio.sleep(interval)
        raise TempMailError(f"TempMail.lol: таймаут ожидания письма для {inbox_data['email']}")


# =========================================================================
# 3. Провайдер GuerrillaMail
# =========================================================================
class GuerrillaMailProvider(BaseTempMailProvider):
    name = "guerrillamail"
    API_BASE = "https://api.guerrillamail.com/ajax.php"

    async def create_inbox(self, session: AsyncSession) -> Dict[str, Any]:
        resp = await session.get(f"{self.API_BASE}?f=get_email_address")
        if resp.status_code != 200:
            raise TempMailError(f"GuerrillaMail create error [{resp.status_code}]")

        data = resp.json()
        email = data.get("email_addr")
        sid = data.get("sid_token")
        if not email or not sid:
            raise TempMailError("GuerrillaMail: invalid response")

        return {
            "provider": self.name,
            "email": email,
            "password": "N/A",
            "sid_token": sid,
        }

    async def wait_for_confirmation_link(
        self,
        session: AsyncSession,
        inbox_data: Dict[str, Any],
        timeout: int = 60,
        interval: int = 3,
    ) -> str:
        sid = inbox_data["sid_token"]
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            resp = await session.get(f"{self.API_BASE}?f=check_email&seq=0&sid_token={sid}")
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("list", [])
                for em in items:
                    subj = (em.get("mail_subject") or "").lower()
                    if "zerotwo" in subj or "confirm" in subj or "magic link" in subj:
                        mail_id = em.get("mail_id")
                        fetch_resp = await session.get(f"{self.API_BASE}?f=fetch_email&email_id={mail_id}&sid_token={sid}")
                        if fetch_resp.status_code == 200:
                            det = fetch_resp.json()
                            content = (det.get("mail_body") or "") + "\n" + (det.get("mail_excerpt") or "")
                            link = extract_confirmation_link(content)
                            if link:
                                return link
            await asyncio.sleep(interval)
        raise TempMailError(f"GuerrillaMail: таймаут ожидания письма для {inbox_data['email']}")


# =========================================================================
# Менеджер TempMail с автоматическим переключением (Failover & Rotation)
# =========================================================================
class TempMailManager:
    """
    Управляет пулом TempMail провайдеров.
    При ошибках или блокировках доменов автоматически переключается на следующий.
    """

    PROVIDERS_MAP = {
        "tempmail_lol": TempMailLolProvider,
        "mail_tm": MailTmProvider,
        "guerrillamail": GuerrillaMailProvider,
    }

    def __init__(self, provider_mode: str = "auto"):
        self.provider_mode = provider_mode.lower()
        self.providers: List[BaseTempMailProvider] = []
        self._setup_providers()
        self._provider_index = 0

    def _setup_providers(self):
        if self.provider_mode in self.PROVIDERS_MAP:
            # Выбран один конкретный провайдер
            self.providers = [self.PROVIDERS_MAP[self.provider_mode]()]
        else:
            # Режим auto: быстрый tempmail_lol -> проверенный mail_tm -> надежный guerrillamail
            self.providers = [
                TempMailLolProvider(),
                MailTmProvider(),
                GuerrillaMailProvider(),
            ]

    def get_providers_chain(self) -> List[BaseTempMailProvider]:
        if len(self.providers) <= 1:
            return self.providers

        # Ротируем стартовый провайдер для распределения доменов
        start = self._provider_index % len(self.providers)
        self._provider_index += 1
        return self.providers[start:] + self.providers[:start]


# Обратная совместимость с существующим кодом
TempMailAccount = TempMailManager
