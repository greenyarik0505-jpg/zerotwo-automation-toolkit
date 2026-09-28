import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import os
from typing import Dict, Any

from autoreg import ZeroTwoAutoreg
from colorama import Fore, Style, init
import open_account
import check_mail

init(autoreset=True)

DEFAULT_CONFIG_FILE = "config.json"


def load_config(config_path: str = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    default_config = {
        "threads": 3,
        "target_count": 5,
        "use_proxies": False,
        "proxy_file": "proxies.txt",
        "proxy_type_default": "http",
        "proxy_rotation": "round_robin",
        "tempmail_provider": "auto",
        "request_timeout": 30,
        "email_poll_timeout": 45,
        "email_poll_interval": 2,
        "accounts_file": "accounts.txt",
        "accounts_json_file": "accounts.json",
        "complete_onboarding": True,
        "default_password": None,
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default_config.update(loaded)
        except Exception as e:
            print(f"{Fore.YELLOW}Внимание: не удалось загрузить {config_path} ({e}), используются дефолты.{Style.RESET_ALL}")
    else:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)

    return default_config


def print_banner():
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}╔════════════════════════════════════════════════════════════╗
║                ZEROTWO AI AUTOREG v1.2                     ║
║           High-Speed Account Generator & Farm              ║
╚════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)


def clear_accounts_data():
    with open("accounts.json", "w", encoding="utf-8") as f:
        f.write("[]\n")
    with open("accounts.txt", "w", encoding="utf-8") as f:
        f.write("")
    print(f"\n{Fore.GREEN}✓ Все аккаунты в accounts.txt и accounts.json успешно очищены!{Style.RESET_ALL}\n")


async def interactive_menu():
    config = load_config()

    while True:
        print_banner()
        print(f" {Fore.YELLOW}[1]{Style.RESET_ALL} 🚀 Запустить авторегер (настроить параметры и старт)")
        print(f" {Fore.YELLOW}[2]{Style.RESET_ALL} 🧪 Быстрый тест (создать 1 тестовый аккаунт)")
        print(f" {Fore.YELLOW}[3]{Style.RESET_ALL} 🌐 Открыть аккаунт в браузере (в 1 клик)")
        print(f" {Fore.YELLOW}[4]{Style.RESET_ALL} 📬 Проверить почту аккаунта (получить свежий Magic Link)")
        print(f" {Fore.YELLOW}[5]{Style.RESET_ALL} 🗑️  Очистить базу аккаунтов (accounts.txt / accounts.json)")
        print(f" {Fore.YELLOW}[0]{Style.RESET_ALL} ❌ Выход\n")

        choice = input(f"{Fore.CYAN}Выберите пункт меню: {Style.RESET_ALL}").strip()

        if choice == "1":
            print(f"\n{Fore.MAGENTA}--- Настройка параметров регистрации ---{Style.RESET_ALL}")

            # 1. Количество аккаунтов
            cnt_input = input(f"Сколько аккаунтов зарегистрировать? [{config.get('target_count', 5)}]: ").strip()
            if cnt_input.isdigit() and int(cnt_input) > 0:
                config["target_count"] = int(cnt_input)

            # 2. Потоки
            thr_input = input(f"Количество потоков? [{config.get('threads', 3)}]: ").strip()
            if thr_input.isdigit() and int(thr_input) > 0:
                config["threads"] = int(thr_input)

            # 3. Прокси
            print("\nИспользовать прокси?")
            print("  [1] Без прокси (напрямую) - по умолчанию")
            print("  [2] Да, использовать прокси из proxies.txt")
            prx_input = input("Выбор [1]: ").strip()
            config["use_proxies"] = (prx_input == "2")

            # 4. Почтовый сервис
            print("\nВыбор сервиса временной почты:")
            print("  [1] Auto (умный пул с авто-переключением) - Рекомендуется")
            print("  [2] TempMail.lol (быстрый, разные домены)")
            print("  [3] Mail.tm")
            print("  [4] GuerrillaMail")
            mail_input = input("Выбор [1]: ").strip()
            mail_map = {
                "1": "auto",
                "2": "tempmail_lol",
                "3": "mail_tm",
                "4": "guerrillamail",
            }
            config["tempmail_provider"] = mail_map.get(mail_input, "auto")

            print(f"\n{Fore.GREEN}Запуск с параметрами: {config['target_count']} аккаунтов | {config['threads']} потоков | Прокси: {config['use_proxies']} | Почта: {config['tempmail_provider']}{Style.RESET_ALL}\n")
            autoreg = ZeroTwoAutoreg(config)
            await autoreg.run()
            input(f"\n{Fore.CYAN}Нажмите Enter, чтобы вернуться в меню...{Style.RESET_ALL}")

        elif choice == "2":
            test_config = dict(config)
            test_config["target_count"] = 1
            test_config["threads"] = 1
            print(f"\n{Fore.CYAN}--- ТЕСТОВЫЙ ЗАПУСК (1 аккаунт) ---{Style.RESET_ALL}\n")
            autoreg = ZeroTwoAutoreg(test_config)
            await autoreg.run()
            input(f"\n{Fore.CYAN}Нажмите Enter, чтобы вернуться в меню...{Style.RESET_ALL}")

        elif choice == "3":
            print()
            open_account.main()
            input(f"\n{Fore.CYAN}Нажмите Enter, чтобы вернуться в меню...{Style.RESET_ALL}")

        elif choice == "4":
            print()
            check_mail.main()
            input(f"\n{Fore.CYAN}Нажмите Enter, чтобы вернуться в меню...{Style.RESET_ALL}")

        elif choice == "5":
            confirm = input(f"\n{Fore.RED}Вы уверены, что хотите удалить ВСЕ аккаунты? (y/n): {Style.RESET_ALL}").strip().lower()
            if confirm in ("y", "yes", "д", "да"):
                clear_accounts_data()
            else:
                print("Отмена очистки.")
            input(f"{Fore.CYAN}Нажмите Enter, чтобы вернуться в меню...{Style.RESET_ALL}")

        elif choice == "0":
            print(f"\n{Fore.YELLOW}До встречи!{Style.RESET_ALL}")
            break
        else:
            print(f"\n{Fore.RED}Неверный пункт меню, попробуйте снова.{Style.RESET_ALL}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="ZeroTwo.ai Automated Account Registration Tool (Autoreg)"
    )
    parser.add_argument(
        "-c", "--count", type=int, default=None, help="Количество аккаунтов для регистрации"
    )
    parser.add_argument(
        "-t", "--threads", type=int, default=None, help="Количество одновременных потоков"
    )
    parser.add_argument(
        "--proxies", dest="use_proxies", action="store_true", default=None, help="Включить прокси"
    )
    parser.add_argument(
        "--no-proxy", dest="use_proxies", action="store_false", default=None, help="Выключить прокси"
    )
    parser.add_argument(
        "-p", "--proxy-file", type=str, default=None, help="Путь к файлу со списком прокси"
    )
    parser.add_argument(
        "-m", "--mail-provider", type=str, choices=["auto", "tempmail_lol", "mail_tm", "guerrillamail"], default=None,
        help="Выбор сервиса временной почты (auto, tempmail_lol, mail_tm, guerrillamail)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Запустить один тестовый пробный рег"
    )
    return parser.parse_args()


async def main():
    # Если аргументы командной строки не переданы, запускаем интерактивное меню
    if len(sys.argv) == 1:
        await interactive_menu()
        return

    # Если переданы аргументы CLI, выполняем команду сразу в фоновом/пакетном режиме
    args = parse_args()
    config = load_config()

    if args.count is not None:
        config["target_count"] = args.count
    if args.threads is not None:
        config["threads"] = args.threads
    if args.use_proxies is not None:
        config["use_proxies"] = args.use_proxies
    if args.proxy_file is not None:
        config["proxy_file"] = args.proxy_file
    if args.mail_provider is not None:
        config["tempmail_provider"] = args.mail_provider

    if args.test:
        config["target_count"] = 1
        config["threads"] = 1
        print(f"{Fore.CYAN}--- РЕЖИМ ТЕСТОВОЙ РЕГИСТРАЦИИ (1 аккаунт) ---{Style.RESET_ALL}")

    autoreg = ZeroTwoAutoreg(config)
    await autoreg.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Процесс остановлен пользователем.{Style.RESET_ALL}")
        sys.exit(0)
