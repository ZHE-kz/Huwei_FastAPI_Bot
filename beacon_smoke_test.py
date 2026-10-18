import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import uuid


BEACON_TYPES = ("enter", "leave", "banner")


def build_beacon_payload(hwid, event_type="enter", user_id="U_TEST_BEACON_USER"):
    if not hwid or len(hwid) > 64:
        raise ValueError("hwid 必須是 1～64 字元")
    if event_type not in BEACON_TYPES:
        raise ValueError(f"event_type 必須是：{', '.join(BEACON_TYPES)}")
    return {
        "destination": "U_TEST_DESTINATION",
        "events": [
            {
                "type": "beacon",
                "mode": "active",
                "timestamp": int(time.time() * 1000),
                "source": {"type": "user", "userId": user_id},
                "webhookEventId": uuid.uuid4().hex,
                "deliveryContext": {"isRedelivery": False},
                "replyToken": "0" * 32,
                "beacon": {"hwid": hwid, "type": event_type},
            }
        ],
    }


def create_signature(body, channel_secret):
    return base64.b64encode(
        hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    ).decode()


def send_payload(webhook_url, payload, channel_secret, allow_remote=False):
    parsed = urllib.parse.urlparse(webhook_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Webhook URL 必須使用 http 或 https")
    if parsed.hostname not in {"127.0.0.1", "localhost"} and not allow_remote:
        raise ValueError("正式網址必須明確加上 --allow-remote")

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    request = urllib.request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": create_signature(body, channel_secret),
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description="產生並測試 LINE Beacon webhook 事件")
    parser.add_argument("--hwid", required=True, help="LINE Beacon hardware ID")
    parser.add_argument("--type", choices=BEACON_TYPES, default="enter")
    parser.add_argument("--user-id", default="U_TEST_BEACON_USER")
    parser.add_argument("--webhook-url", help="省略時只輸出 payload，不送出")
    parser.add_argument("--secret-env", default="LINE_CHANNEL_SECRET")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()

    payload = build_beacon_payload(args.hwid, args.type, args.user_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.webhook_url:
        print("\nDRY RUN：未送出 webhook。")
        return

    channel_secret = os.environ.get(args.secret_env, "")
    if not channel_secret:
        raise SystemExit(f"缺少環境變數：{args.secret_env}")
    status, response_body = send_payload(
        args.webhook_url,
        payload,
        channel_secret,
        args.allow_remote,
    )
    print(f"\nHTTP {status}\n{response_body}")


if __name__ == "__main__":
    main()
