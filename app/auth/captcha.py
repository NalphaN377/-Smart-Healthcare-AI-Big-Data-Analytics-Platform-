"""一次性登录图形验证码。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import secrets
import time

from flask import current_app, session

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
LIFETIME_SECONDS = 120
SESSION_KEY = "login_captcha"


def _digest(nonce: str, code: str) -> str:
    key = str(current_app.secret_key).encode("utf-8")
    return hmac.new(key, f"{nonce}:{code.upper()}".encode("utf-8"), hashlib.sha256).hexdigest()


def _svg(code: str) -> str:
    # 所有动态字符均来自固定字母表；仍转义以保持生成器边界安全。
    letters = []
    for index, char in enumerate(code):
        x = 27 + index * 32
        rotation = (-9, 6, -4, 8, -6)[index]
        letters.append(
            f'<text x="{x}" y="43" transform="rotate({rotation} {x} 43)">{html.escape(char)}</text>'
        )
    noise = "".join(
        f'<path d="M {secrets.randbelow(35)} {10 + secrets.randbelow(40)} '
        f'Q {55 + secrets.randbelow(70)} {secrets.randbelow(58)} {165 + secrets.randbelow(25)} {10 + secrets.randbelow(40)}"/>'
        for _ in range(3)
    )
    dots = "".join(
        f'<circle cx="{secrets.randbelow(198)}" cy="{secrets.randbelow(58)}" r="1"/>' for _ in range(22)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="58" viewBox="0 0 200 58">'
        '<rect width="200" height="58" rx="8" fill="#eef7f6"/>'
        f'<g fill="#7bbab4" opacity=".45">{dots}</g>'
        f'<g fill="none" stroke="#78aaa5" stroke-width="1.2" opacity=".5">{noise}</g>'
        f'<g fill="#205d59" font-family="Consolas,monospace" font-size="30" font-weight="700" '
        f'letter-spacing="4">{"".join(letters)}</g></svg>'
    )


def issue() -> dict:
    """生成验证码并把不可逆摘要绑定到当前 Flask Session。"""
    code = "".join(secrets.choice(ALPHABET) for _ in range(5))
    nonce = secrets.token_urlsafe(18)
    session[SESSION_KEY] = {
        "digest": _digest(nonce, code),
        "nonce": nonce,
        "expires_at": int(time.time()) + LIFETIME_SECONDS,
    }
    encoded = base64.b64encode(_svg(code).encode("utf-8")).decode("ascii")
    return {"image": f"data:image/svg+xml;base64,{encoded}", "expires_in": LIFETIME_SECONDS}


def verify(value: str) -> tuple[bool, str]:
    """消费验证码。无论成功或失败，同一验证码都不能再次使用。"""
    challenge = session.pop(SESSION_KEY, None)
    normalized = str(value or "").strip().upper()
    if not normalized:
        return False, "请输入验证码"
    if not challenge or int(challenge.get("expires_at", 0)) < int(time.time()):
        return False, "验证码已过期，请刷新后重试"
    expected = _digest(str(challenge.get("nonce", "")), normalized)
    if not hmac.compare_digest(expected, str(challenge.get("digest", ""))):
        return False, "验证码错误，请重新输入"
    return True, ""
