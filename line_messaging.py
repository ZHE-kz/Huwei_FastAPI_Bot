import re


LINE_TEXT_LIMIT = 4900
LINE_REPLY_MESSAGE_LIMIT = 5
_BREAK_RE = re.compile(r"[\n。！？!?；;.]" )


def split_line_text(text: str, limit: int = LINE_TEXT_LIMIT) -> list[str]:
    text = str(text or "").strip()
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        window = text[:limit]
        breakpoints = [match.end() for match in _BREAK_RE.finditer(window)]
        cut = breakpoints[-1] if breakpoints and breakpoints[-1] >= limit // 2 else limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def fit_line_text_with_footer(text: str, footer: str, limit: int = LINE_TEXT_LIMIT) -> str:
    footer = str(footer or "").strip()
    suffix = f"\n\n{footer}" if footer else ""
    if len(suffix) >= limit:
        return suffix[-limit:].lstrip()
    available = limit - len(suffix)
    body = str(text or "").strip()
    if len(body) > available:
        body = split_line_text(body, max(1, available - 1))[0].rstrip() + "…"
    return f"{body}{suffix}"


def fit_line_reply_payload(payload: dict) -> dict:
    """Keep every LINE text message valid and the reply at five messages or fewer."""
    messages = list(payload.get("messages") or [])
    non_text_count = min(
        sum(message.get("type") != "text" for message in messages),
        LINE_REPLY_MESSAGE_LIMIT,
    )
    remaining_text_slots = LINE_REPLY_MESSAGE_LIMIT - non_text_count
    fitted = []

    for message in messages:
        if message.get("type") != "text":
            if len(fitted) < LINE_REPLY_MESSAGE_LIMIT:
                fitted.append(message)
            continue
        if remaining_text_slots <= 0:
            continue

        chunks = split_line_text(message.get("text", ""))
        selected = chunks[:remaining_text_slots]
        for index, chunk in enumerate(selected):
            part = {**message, "text": chunk}
            if index < len(selected) - 1:
                part.pop("quickReply", None)
            fitted.append(part)
        remaining_text_slots -= len(selected)

    return {**payload, "messages": fitted[:LINE_REPLY_MESSAGE_LIMIT]}
