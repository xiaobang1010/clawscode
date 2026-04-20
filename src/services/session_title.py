from __future__ import annotations

import re


MAX_TITLE_LENGTH = 80


def generate_title(first_user_message: str) -> str:
    if not first_user_message:
        return "新会话"

    text = first_user_message.strip()

    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("//"):
            text = line
            break

    text = re.sub(r"[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "新会话"

    if len(text) > MAX_TITLE_LENGTH:
        text = text[:MAX_TITLE_LENGTH].rsplit(" ", 1)[0]
        if len(text) > MAX_TITLE_LENGTH - 3:
            text = text[:MAX_TITLE_LENGTH - 3]
        text = text.rstrip() + "..."

    return text


def clean_title(title: str) -> str:
    title = re.sub(r"[<>:\"/\\|?*]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title[:MAX_TITLE_LENGTH] if len(title) > MAX_TITLE_LENGTH else title
