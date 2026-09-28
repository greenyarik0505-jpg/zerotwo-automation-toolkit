import argparse
import json
import os
import re
import sys
import webbrowser
import requests
import quopri

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def extract_link(content: str) -> str | None:
    if "=3D" in content or "=\r\n" in content or "=\n" in content:
        try:
            content = quopri.decodestring(content.encode("utf-8", errors="ignore")).decode("utf-8", errors="ignore")
        except Exception:
            pass

    def clean(u: str) -> str:
        return u.rstrip("]>.)\"'").strip()

    sendgrid_matches = re.findall(r"https://[a-zA-Z0-9.\-_]*sendgrid\.net/ls/click\?[^\s\"'<>\[\]]+", content)
    if sendgrid_matches:
        return clean(sendgrid_matches[0])

    direct_matches = re.findall(r"https://db\.zerotwo\.ai/auth/v1/verify\?[^\s\"'<>\[\]]+", content)
    if direct_matches:
        return clean(direct_matches[0])

    return None


def resolve_auth_link(link: str) -> str:
    s = requests.Session()
    curr = link
    for _ in range(5):
        r = s.get(curr, allow_redirects=False)
        loc = r.headers.get("Location") or r.headers.get("location")
        if not loc:
            break
        if "access_token=" in loc or "refresh_token=" in loc:
            return loc
        curr = loc
    return curr


def check_mail_for_account(acc: dict, open_in_browser: bool = True):
    email = acc.get("email")
    provider = acc.get("tempmail_provider", "mail_tm")
    auth_data = acc.get("tempmail_auth", {})
    print(f"\nПодключаемся к ящику {email} [Провайдер: {provider}]...")

    raw_link = None

    # 1. TempMail.lol
    if provider == "tempmail_lol":
        token = auth_data.get("token")
        if not token:
            print("Ошибка: токен почты tempmail_lol не найден.")
            return
        r = requests.get(f"https://api.tempmail.lol/v2/inbox?token={token}")
        if r.status_code != 200:
            print(f"Ошибка обращения к TempMail.lol: {r.status_code}")
            return
        emails = r.json().get("emails", [])
        if not emails:
            print("В ящике пока нет входящих писем.")
            return
        latest = emails[0]
        print(f"Получено письмо: '{latest.get('subject')}'")
        body = (latest.get("body") or "") + "\n" + (latest.get("html") or "")
        raw_link = extract_link(body)

    # 2. GuerrillaMail
    elif provider == "guerrillamail":
        sid = auth_data.get("sid_token")
        if not sid:
            print("Ошибка: sid_token для GuerrillaMail не найден.")
            return
        r = requests.get(f"https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid}")
        if r.status_code != 200:
            print(f"Ошибка обращения к GuerrillaMail: {r.status_code}")
            return
        items = r.json().get("list", [])
        zerotwo_items = [e for e in items if "zerotwo" in e.get("mail_subject", "").lower() or "confirm" in e.get("mail_subject", "").lower() or "magic link" in e.get("mail_subject", "").lower()]
        if not zerotwo_items:
            print("В ящике пока нет писем от ZeroTwo.")
            return
        mail_id = zerotwo_items[0].get("mail_id")
        fetch_r = requests.get(f"https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={mail_id}&sid_token={sid}")
        det = fetch_r.json()
        print(f"Получено письмо: '{zerotwo_items[0].get('mail_subject')}'")
        body = (det.get("mail_body") or "") + "\n" + (det.get("mail_excerpt") or "")
        raw_link = extract_link(body)

    # 3. Mail.tm (по умолчанию)
    else:
        pwd = acc.get("tempmail_password") or auth_data.get("password")
        token = auth_data.get("token")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            r_token = requests.post("https://api.mail.tm/token", json={"address": email, "password": pwd})
            if r_token.status_code != 200:
                print(f"Ошибка авторизации Mail.tm: {r_token.status_code}")
                return
            token = r_token.json()["token"]
            headers["Authorization"] = f"Bearer {token}"

        r_msgs = requests.get("https://api.mail.tm/messages", headers=headers)
        if r_msgs.status_code != 200:
            print(f"Ошибка получения сообщений: {r_msgs.status_code}")
            return
        msgs = r_msgs.json()
        items = msgs if isinstance(msgs, list) else msgs.get("hydra:member", [])
        if not items:
            print("В ящике пока нет входящих писем.")
            return
        latest_id = items[0]["id"]
        r_det = requests.get(f"https://api.mail.tm/messages/{latest_id}", headers=headers)
        det = r_det.json()
        print(f"Получено письмо: '{items[0].get('subject')}'")
        body = (det.get("text") or "") + "\n" + str(det.get("html") or "")
        raw_link = extract_link(body)

    if not raw_link:
        print("Не удалось извлечь ссылку из письма.")
        return

    print("Резолвим конечный URL авторизации...")
    final_url = resolve_auth_link(raw_link)

    print("\n=======================================================")
    print("   ГОТОВАЯ ССЫЛКА ДЛЯ ВХОДА (MAGIC LINK):             ")
    print("=======================================================")
    print(final_url)
    print("=======================================================\n")

    if open_in_browser:
        print("Открываем браузер с аккаунтом...")
        webbrowser.open(final_url)


def main():
    parser = argparse.ArgumentParser(description="Проверка входящих писем и Magic Link для аккаунтов")
    parser.add_argument("-e", "--email", type=str, default=None, help="Email аккаунта")
    parser.add_argument("--no-open", action="store_true", help="Не открывать автоматически в браузере")
    args = parser.parse_args()

    if not os.path.exists("accounts.json"):
        print("Файл accounts.json не найден.")
        return

    with open("accounts.json", "r", encoding="utf-8") as f:
        accounts = json.load(f)

    if not accounts:
        print("Список аккаунтов пуст.")
        return

    target_acc = None
    if args.email:
        for acc in accounts:
            if acc.get("email") == args.email:
                target_acc = acc
                break
        if not target_acc:
            print(f"Аккаунт {args.email} не найден в accounts.json.")
            return
    else:
        print("Выберите аккаунт для проверки почты:")
        for idx, acc in enumerate(accounts, 1):
            print(f"[{idx}] {acc.get('email')} ({acc.get('tempmail_provider', 'mail_tm')})")

        choice = input("\nНомер аккаунта (или Enter для первого): ").strip()
        idx = 0
        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            idx = int(choice) - 1
        target_acc = accounts[idx]

    check_mail_for_account(
        acc=target_acc,
        open_in_browser=not args.no_open,
    )


if __name__ == "__main__":
    main()
