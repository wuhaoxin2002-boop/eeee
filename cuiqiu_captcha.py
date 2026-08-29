#!/usr/bin/env python3
import json
import os
import re
import base64
import time
import html
from email import policy
from email.parser import BytesParser
import sys
from pathlib import Path

import ddddocr
import cv2
import numpy as np
import requests

BASE = "https://mail-client-api.cuiqiu.com"
ROOT = Path(__file__).resolve().parent
COOKIE_FILE = ROOT / ".cuiqiu-cookies"
IMAGE_FILE = ROOT / "captcha.png"


def fetch_latest_code(mail, password):
    """Run the existing login/mail workflow and return its final code."""
    import subprocess
    import sys as _sys
    import re as _re
    result = subprocess.run(
        [_sys.executable, str(Path(__file__).resolve()), mail, password],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "请求失败")
    lines = [line.strip() for line in result.stdout.splitlines()]
    for line in reversed(lines):
        if _re.fullmatch(r"\d{6}", line):
            return line
    return None


def request(session, url, **kwargs):
    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": "https://mail.cuiqiu.com",
        "referer": "https://mail.cuiqiu.com/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/152 Safari/537.36",
    }
    headers.update(kwargs.pop("headers", {}))
    method = kwargs.pop("method", "GET")
    for attempt in range(3):
        try:
            response = session.request(method=method, url=url, headers=headers, timeout=20, **kwargs)
            break
        except requests.exceptions.SSLError:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    response.raise_for_status()
    return response


def normalize(text):
    text = re.sub(r"\s+", "", text)
    return (text.replace("x", "*").replace("X", "*").replace("×", "*")
                .replace("÷", "/").replace("−", "-").replace("O", "0")
                .replace("I", "1").replace("l", "1"))


def calculate(expression):
    if not re.fullmatch(r"[0-9]+(?:[+*/%-][0-9]+)+", expression):
        return None
    try:
        return eval(expression, {"__builtins__": {}}, {})
    except Exception:
        return None


def find_verification_code(value):
    """Find a six-digit code in any nested message field."""
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    candidates = []
    body_candidates = []

    # The source endpoint returns URL-safe Base64 in raw_source_base64.
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        encoded = value["data"].get("raw_source_base64")
        if encoded:
            try:
                text = base64.urlsafe_b64decode(encoded + "===").decode("utf-8", "ignore")
            except Exception:
                pass

    def collect(item):
        if isinstance(item, str):
            candidates.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                collect(child)
    collect(value)
    candidates.extend([text, html.unescape(text)])
    # Parse raw MIME source when the API returns the complete message.
    try:
        message = BytesParser(policy=policy.default).parsebytes(text.encode("utf-8", "ignore"))
        for part in message.walk():
            payload = part.get_payload(decode=True)
            if payload:
                body_candidates.append(payload.decode(part.get_content_charset() or "utf-8", "ignore"))
    except Exception:
        pass
    for token in re.findall(r"[A-Za-z0-9+/=_-]{24,}", text):
        try:
            decoded = base64.urlsafe_b64decode(token + "===").decode("utf-8", "ignore")
            candidates.append(decoded)
            candidates.append(html.unescape(decoded))
            # MIME bodies may themselves be Base64 encoded.
            for body_token in re.findall(r"[A-Za-z0-9+/=_-]{20,}", decoded):
                try:
                    candidates.append(base64.b64decode(body_token + "===").decode("utf-8", "ignore"))
                except Exception:
                    pass
        except Exception:
            pass
    # Search decoded body first; headers contain unrelated timestamps and IDs.
    for candidate in body_candidates:
        plain = re.sub(r"<[^>]+>", " ", html.unescape(candidate))
        focused = re.findall(r"(?:验证码|校验码|verification\s*code)[^0-9]{0,40}(\d{6})", plain, re.I)
        if focused:
            return focused[0]
        matches = re.findall(r"(?<!\d)\d{6}(?!\d)", plain)
        if matches:
            return matches[0]
    for candidate in candidates:
        # Prefer codes explicitly described as verification codes.
        focused = re.findall(r"(?:验证码|verify(?:ing|ication)?[^0-9]{0,20})[^0-9]{0,20}(\d{6})", candidate, re.I)
        if focused:
            return focused[0]
        matches = re.findall(r"(?<!\d)\d{6}(?!\d)", candidate)
        if matches:
            return matches[0]
    return None


def recognize_variants(image):
    source = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    variants = [image]
    if source is not None:
        enlarged = cv2.resize(source, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        variants.append(cv2.imencode('.png', gray)[1].tobytes())
        # Captcha glyphs are green; extracting that channel suppresses much of the noise.
        green = enlarged[:, :, 1]
        for threshold in (40, 70, 100, 130):
            _, binary = cv2.threshold(green, threshold, 255, cv2.THRESH_BINARY)
            variants.append(cv2.imencode('.png', binary)[1].tobytes())

    ocr = ddddocr.DdddOcr(show_ad=False)
    results = []
    for item in variants:
        text = ocr.classification(item).strip()
        if text:
            results.append(text)
    if not results:
        return ""
    # Prefer the most frequent result; ties favor the least transformed source.
    counts = {}
    for text in results:
        counts[text] = counts.get(text, 0) + 1
    return max(counts, key=lambda value: (counts[value], -results.index(value)))


def main():
    mail = sys.argv[1] if len(sys.argv) > 1 else "l8001@zhr002.com"
    password = sys.argv[2] if len(sys.argv) > 2 else os.getenv("CUIQIU_PASSWORD")
    session = requests.Session()
    if COOKIE_FILE.exists():
        session.headers["Cookie"] = COOKIE_FILE.read_text().strip()

    form = {"mail": mail, "language": "zh-CN", "host": "mail.cuiqiu.com",
            "browser_language": "zh-CN", "browser_time_zone": "Asia/Shanghai"}
    route = request(session, f"{BASE}/v1/mail/route/resolve", method="POST", data=form).json()
    print("route:", json.dumps(route, ensure_ascii=False, indent=2))
    if not password:
        print("请提供密码：命令行第二个参数或 CUIQIU_PASSWORD 环境变量")
        return

    attempt = 0
    while True:
        attempt += 1
        print(f"\n第 {attempt} 次尝试")
        captcha = request(session, f"{BASE}/v1/captcha/get", method="POST", data={k: form[k] for k in form if k != "mail"}).json()
        print("captcha:", json.dumps(captcha, ensure_ascii=False, indent=2))
        image_url = f"{BASE}/v1{captcha['data']['image_url']}"
        image = request(session, image_url, headers={"accept": "image/*"}).content
        IMAGE_FILE.write_bytes(image)
        COOKIE_FILE.write_text("; ".join(f"{c.name}={c.value}" for c in session.cookies))
        print(f"验证码图片已保存：{IMAGE_FILE}")

        raw = recognize_variants(image)
        expression = normalize(raw)
        answer = calculate(expression)
        print("OCR 原文:", repr(raw))
        print("验证码表达式:", expression or "(未识别)")
        print("验证码答案:", answer if answer is not None else "(请人工确认)")

        captcha_value = str(answer) if answer is not None else expression
        if not captcha_value:
            continue

        login_form = {
        "mail": mail,
        "password": password,
        "captcha_id": captcha["data"]["captcha_id"],
        "captcha_value": captcha_value,
        "language": "zh-CN",
        "host": "mail.cuiqiu.com",
        "browser_language": "zh-CN",
        "browser_time_zone": "Asia/Shanghai",
        }
        try:
            login_response = request(session, f"{BASE}/v1/session/login", method="POST", data=login_form)
            login = login_response.json()
        except requests.HTTPError as error:
            response = error.response
            try:
                login = response.json()
            except ValueError:
                login = {"code": response.status_code, "msg": response.text[:500]}
        print("login:", json.dumps(login, ensure_ascii=False, indent=2))
        login_data = login.get("data") if isinstance(login, dict) else None
        if (isinstance(login, dict) and login.get("code") == 200) or (
            isinstance(login_data, dict) and login_data.get("access_token")
        ):
            COOKIE_FILE.write_text("; ".join(f"{c.name}={c.value}" for c in session.cookies))
            print("登录成功")
            token = login_data.get("access_token") if isinstance(login_data, dict) else None
            api_base = route.get("data", {}).get("orange_api_url", BASE).rstrip("/")
            list_form = {
                "folder": "INBOX", "cursor": "", "limit": "15", "keyword": "",
                "subject": "", "body": "", "from": "support@tfent.cn", "to": "", "date_from": "",
                "date_to": "", "flagged": "all", "read_status": "all",
                "has_attachment": "all", "use_threads": "0", **{k: form[k] for k in ("language", "host", "browser_language", "browser_time_zone")},
            }
            message_headers = {"content-type": "application/x-www-form-urlencoded"}
            if token:
                message_headers["authorization"] = f"Bearer {token}"
            try:
                messages = request(session, f"{api_base}/v1/message/scroll/list", method="POST", data=list_form, headers=message_headers).json()
                items = messages.get("data", {}).get("list", []) if isinstance(messages, dict) else []
                items = [item for item in items if any(
                    str(sender.get("address", "")).lower() == "support@tfent.cn"
                    for sender in item.get("from", [])
                )] or items
                items.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
                code = None
                for item in items:
                    source_form = {"folder": "INBOX", "id": str(item.get("id", "")), **{k: form[k] for k in ("language", "host", "browser_language", "browser_time_zone")}}
                    try:
                        source = request(session, f"{api_base}/v1/message/source", method="POST", data=source_form, headers=message_headers).json()
                        code = find_verification_code(source)
                    except requests.RequestException:
                        continue
                    if code:
                        break
                print(code or "未找到")
            except requests.HTTPError as error:
                print("message_list 请求失败:", error.response.text[:1000])
            return
        print("登录失败，重新获取验证码重试…")


if __name__ == "__main__":
    main()
