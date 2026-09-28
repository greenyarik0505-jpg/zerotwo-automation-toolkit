import json
import os
import sys
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ACCOUNTS_FILE = "accounts.json"


def get_login_url(acc: dict) -> str:
    access_token = acc.get("access_token")
    refresh_token = acc.get("refresh_token")
    return (
        f"https://app.zerotwo.ai/auth/callback"
        f"#access_token={access_token}&refresh_token={refresh_token}&token_type=bearer&type=signup"
    )


def main():
    if not os.path.exists(ACCOUNTS_FILE):
        print(f"Файл {ACCOUNTS_FILE} не найден. Сначала запустите регистрацию через main.py.")
        return

    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    if not accounts:
        print("В файле нет зарегистрированных аккаунтов.")
        return

    print("========================================")
    print("   ZeroTwo: Выберите аккаунт для входа  ")
    print("========================================")
    for idx, acc in enumerate(accounts, 1):
        print(f"[{idx}] {acc.get('email')} | Пароль: {acc.get('password')}")

    choice = input("\nВведите номер аккаунта для входа (или Enter для первого): ").strip()
    idx = 0
    if choice.isdigit() and 1 <= int(choice) <= len(accounts):
        idx = int(choice) - 1

    selected = accounts[idx]
    login_url = get_login_url(selected)

    print("\n----------------------------------------")
    print(f"Аккаунт: {selected.get('email')}")
    print(f"Пароль:  {selected.get('password')}")
    print("----------------------------------------")
    print("\nПрямая ссылка для мгновенного входа в браузер (без ввода логина/пароля):")
    print(login_url)
    print("\nОткрываем браузер...")
    webbrowser.open(login_url)


if __name__ == "__main__":
    main()
