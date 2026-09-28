import itertools
import random
import re
from typing import Optional, List


class ProxyManager:
    """
    Универсальный менеджер прокси.
    Поддерживает: HTTP, HTTPS, SOCKS4, SOCKS5.
    Парсит все популярные форматы:
      - protocol://user:pass@host:port
      - protocol://host:port
      - host:port:user:pass
      - user:pass@host:port
      - host:port
    """

    def __init__(
        self,
        proxy_file: str = "proxies.txt",
        default_protocol: str = "http",
        rotation: str = "round_robin",
    ):
        self.proxy_file = proxy_file
        self.default_protocol = default_protocol.lower().replace("://", "")
        self.rotation = rotation.lower()
        self.proxies: List[str] = []
        self._cycler = None
        self.load_proxies()

    def parse_proxy(self, raw_line: str) -> Optional[str]:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            return None

        # 1. Если уже есть протокол: protocol://...
        if re.match(r"^[a-zA-Z0-9]+://", line):
            return line

        # 2. Формат host:port:user:pass
        parts = line.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"{self.default_protocol}://{user}:{password}@{host}:{port}"

        # 3. Формат user:pass@host:port
        if "@" in line and len(parts) >= 2:
            return f"{self.default_protocol}://{line}"

        # 4. Формат host:port
        if len(parts) == 2:
            host, port = parts
            return f"{self.default_protocol}://{host}:{port}"

        return f"{self.default_protocol}://{line}"

    def load_proxies(self) -> int:
        self.proxies = []
        try:
            with open(self.proxy_file, "r", encoding="utf-8") as f:
                for line in f:
                    proxy = self.parse_proxy(line)
                    if proxy:
                        self.proxies.append(proxy)
        except FileNotFoundError:
            pass

        if self.proxies:
            self._cycler = itertools.cycle(self.proxies)
        else:
            self._cycler = None

        return len(self.proxies)

    def get_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None

        if self.rotation == "random":
            return random.choice(self.proxies)
        else:
            if self._cycler is None:
                self._cycler = itertools.cycle(self.proxies)
            return next(self._cycler)

    def count(self) -> int:
        return len(self.proxies)
