import asyncio
import datetime
import json
import os
import random
import string
from typing import Dict, Any, Optional, List
from colorama import Fore, Style, init
from curl_cffi.requests import AsyncSession

from proxy_manager import ProxyManager
from tempmail import TempMailManager, TempMailError
from zerotwo_client import ZeroTwoClient, ZeroTwoError

init(autoreset=True)


class ZeroTwoAutoreg:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.threads = config.get("threads", 3)
        self.target_count = config.get("target_count", 5)
        self.use_proxies = config.get("use_proxies", False)
        self.proxy_file = config.get("proxy_file", "proxies.txt")
        self.proxy_type_default = config.get("proxy_type_default", "http")
        self.proxy_rotation = config.get("proxy_rotation", "round_robin")
        self.tempmail_provider = config.get("tempmail_provider", "auto")
        self.request_timeout = config.get("request_timeout", 30)
        self.email_poll_timeout = config.get("email_poll_timeout", 45)
        self.email_poll_interval = config.get("email_poll_interval", 2)
        self.accounts_file = config.get("accounts_file", "accounts.txt")
        self.accounts_json_file = config.get("accounts_json_file", "accounts.json")
        self.complete_onboarding = config.get("complete_onboarding", True)
        self.default_password = config.get("default_password", None)

        self.proxy_mgr = ProxyManager(
            proxy_file=self.proxy_file,
            default_protocol=self.proxy_type_default,
            rotation=self.proxy_rotation,
        )
        self.tempmail_mgr = TempMailManager(provider_mode=self.tempmail_provider)

        self.success_count = 0
        self.fail_count = 0
        self._lock = asyncio.Lock()

    def generate_password(self) -> str:
        if self.default_password:
            return self.default_password
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return "Z2_" + "".join(random.choices(chars, k=14))

    def generate_name(self) -> str:
        first_names = [
            "Alex", "Jordan", "Sam", "Chris", "Taylor", "Morgan", "Casey",
            "Robin", "Drew", "Cameron", "Jamie", "Skyler", "Jesse", "Pat",
            "Logan", "Avery", "Riley", "Hayden", "Rowan", "Finley"
        ]
        last_names = [
            "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller",
            "Davis", "Wilson", "Anderson", "Taylor", "Thomas", "Moore",
            "Jackson", "Martin", "Lee", "Perez", "Thompson", "White"
        ]
        return f"{random.choice(first_names)} {random.choice(last_names)}"

    async def register_single(self, index: int) -> Optional[Dict[str, Any]]:
        proxy = self.proxy_mgr.get_proxy() if self.use_proxies else None
        proxy_info = f" [{proxy}]" if proxy else " [Direct]"

        print(f"{Fore.CYAN}[#{index}] Начинаем регистрацию...{proxy_info}{Style.RESET_ALL}")

        session_kwargs = {
            "impersonate": "chrome124",
            "timeout": self.request_timeout,
        }
        if proxy:
            session_kwargs["proxy"] = proxy

        providers_chain = self.tempmail_mgr.get_providers_chain()

        async with AsyncSession(**session_kwargs) as session:
            last_err = None

            for provider in providers_chain:
                try:
                    p_name = provider.name
                    print(f"{Fore.BLUE}[#{index}] Пробуем почтовый сервис: {p_name}...{Style.RESET_ALL}")

                    # 1. Создаем почтовый ящик
                    inbox_data = await provider.create_inbox(session)
                    email = inbox_data["email"]
                    print(f"{Fore.GREEN}[#{index}] Почта создана ({p_name}): {email}{Style.RESET_ALL}")

                    password = self.generate_password()
                    full_name = self.generate_name()

                    # 2. Отправляем запрос на регистрацию ZeroTwo
                    print(f"{Fore.BLUE}[#{index}] Отправляем запрос на регистрацию ZeroTwo...{Style.RESET_ALL}")
                    signup_res = await ZeroTwoClient.signup(
                        session=session,
                        email=email,
                        password=password,
                        display_name=full_name,
                    )
                    user_id = signup_res.get("id")
                    print(f"{Fore.GREEN}[#{index}] Регистрация принята ZeroTwo! User ID: {user_id}{Style.RESET_ALL}")

                    # 3. Ожидаем письмо с подтверждением
                    print(f"{Fore.YELLOW}[#{index}] Ожидаем письмо с подтверждением ({p_name}, до {self.email_poll_timeout}с)...{Style.RESET_ALL}")
                    confirm_link = await provider.wait_for_confirmation_link(
                        session=session,
                        inbox_data=inbox_data,
                        timeout=self.email_poll_timeout,
                        interval=self.email_poll_interval,
                    )
                    print(f"{Fore.GREEN}[#{index}] Письмо получено! Активируем аккаунт...{Style.RESET_ALL}")

                    # 4. Переходим по ссылке подтверждения и получаем токены
                    access_token, refresh_token = await ZeroTwoClient.verify_confirmation_link(
                        session=session,
                        link=confirm_link,
                    )
                    print(f"{Fore.GREEN}[#{index}] Аккаунт активирован! Токены получены.{Style.RESET_ALL}")

                    # 5. Завершаем онбординг профиля
                    if self.complete_onboarding and user_id:
                        print(f"{Fore.BLUE}[#{index}] Завершаем онбординг профиля...{Style.RESET_ALL}")
                        await ZeroTwoClient.complete_onboarding(session, access_token, user_id)

                    login_url = (
                        f"https://app.zerotwo.ai/auth/callback"
                        f"#access_token={access_token}&refresh_token={refresh_token}&token_type=bearer&type=signup"
                    )

                    account_data = {
                        "email": email,
                        "password": password,
                        "login_url": login_url,
                        "login_note": "Вход по паролю на сайте zerotwo.ai недоступен (поле пароля отсутствует в форме входа). Для входа в аккаунт перейдите по ссылке login_url (вставить в адресную строку браузера).",
                        "user_id": user_id,
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "tempmail_provider": p_name,
                        "tempmail_auth": {k: v for k, v in inbox_data.items() if k not in ("email",)},
                        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "proxy_used": proxy,
                    }

                    # 6. Сохраняем результат
                    async with self._lock:
                        self.save_account(account_data)
                        self.success_count += 1

                    print(
                        f"{Fore.GREEN}{Style.BRIGHT}[#{index}] УСПЕШНО ЗАРЕГИСТРИРОВАН: "
                        f"{email} | {password} [Провайдер: {p_name}]{Style.RESET_ALL}"
                    )
                    print(f"{Fore.YELLOW}[#{index}] Ссылка для входа: {login_url}{Style.RESET_ALL}")
                    return account_data

                except Exception as e:
                    last_err = e
                    print(f"{Fore.YELLOW}[#{index}] Провайдер {provider.name} вернул ошибку ({e}). Автоматически переключаемся на резервный...{Style.RESET_ALL}")
                    continue

            # Если все провайдеры в цепочке потерпели неудачу
            async with self._lock:
                self.fail_count += 1
            print(f"{Fore.RED}[#{index}] Все почтовые провайдеры исчерпаны. Последняя ошибка: {last_err}{Style.RESET_ALL}")
            return None

    def save_account(self, acc: Dict[str, Any]):
        # 1. Сохранение в accounts.json
        accounts_list = []
        if os.path.exists(self.accounts_json_file):
            try:
                with open(self.accounts_json_file, "r", encoding="utf-8") as f:
                    accounts_list = json.load(f)
            except Exception:
                accounts_list = []

        accounts_list.append(acc)
        with open(self.accounts_json_file, "w", encoding="utf-8") as f:
            json.dump(accounts_list, f, indent=2, ensure_ascii=False)

        account_num = len(accounts_list)

        # 2. Сохранение в accounts.txt в наглядном формате
        block = (
            "=========================================\n"
            f"АККАУНТ {account_num}\n"
            "=========================================\n"
            f"Почта (твой главный логин): {acc['email']}\n"
            f"Пароль (Не работает етот метод входа): {acc['password']}\n"
            f"Ссилка для входа: {acc['login_url']}\n\n"
        )
        with open(self.accounts_file, "a", encoding="utf-8") as f:
            f.write(block)

    async def run(self):
        print(f"\n{Fore.MAGENTA}{Style.BRIGHT}========================================{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}{Style.BRIGHT}   ZeroTwo AI Autoreg Engine v1.1       {Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}{Style.BRIGHT}   (Multi-Provider TempMail Edition)    {Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}{Style.BRIGHT}========================================{Style.RESET_ALL}")
        print(f"Целевое количество: {self.target_count}")
        print(f"Количество потоков: {self.threads}")
        print(f"Почтовый режим:     {self.tempmail_provider.upper()} (Пул: TempMail.lol, Mail.tm, GuerrillaMail)")
        print(f"Использование прокси: {self.use_proxies} ({self.proxy_mgr.count()} загружено)")
        print(f"Файл вывода:        {self.accounts_file} и {self.accounts_json_file}\n")

        semaphore = asyncio.Semaphore(self.threads)

        async def worker(idx: int):
            async with semaphore:
                await self.register_single(idx)

        tasks = [worker(i + 1) for i in range(self.target_count)]
        await asyncio.gather(*tasks)

        print(f"\n{Fore.CYAN}{Style.BRIGHT}========================================{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Успешно создано аккаунтов: {self.success_count}{Style.RESET_ALL}")
        print(f"{Fore.RED}Ошибок при создании:       {self.fail_count}{Style.RESET_ALL}")
        print(f"Все данные сохранены в {self.accounts_file} и {self.accounts_json_file}")
        print(f"{Fore.CYAN}{Style.BRIGHT}========================================\n{Style.RESET_ALL}")
