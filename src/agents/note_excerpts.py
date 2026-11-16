"""Choose short, verbatim note passages for excerpt-only Writer drafts."""
from __future__ import annotations

import re

from src.agents.researcher import NOTE_TOPIC_PHRASES, _normalize_note_text


def _matches_topic(task, passage: str) -> bool:
    topic = next((part for part in task.task_id.split(":")
                  if part in NOTE_TOPIC_PHRASES), None)
    normalized = _normalize_note_text(passage)
    phrases = NOTE_TOPIC_PHRASES.get(topic, (_normalize_note_text(task.query),))
    if topic == "auditor":
        return False
    if topic == "business":
        return any(phrase in normalized for phrase in
                   ("nganh nghe kinh doanh", "kinh doanh trong linh vuc",
                    "hoat dong chinh cua"))
    if topic == "depreciation":
        return any(phrase in normalized for phrase in
                   ("phuong phap khau hao", "khau hao theo phuong phap",
                    "thoi gian su dung huu ich", "thoi gian huu dung"))
    if topic == "borrowing_policy":
        return ("khoan vay" in normalized and
                any(phrase in normalized for phrase in
                    ("lai suat", "ky han", "dao han")))
    if topic == "provisions":
        return any(phrase in normalized for phrase in
                   ("trich lap du phong", "du phong phai thu kho doi duoc lap",
                    "du phong giam gia duoc lap"))
    if topic == "opinion":
        return ("theo y kien cua chung toi" in normalized and
                "phan anh trung thuc" in normalized)
    if topic == "commitments":
        return any(phrase in normalized for phrase in (
            "nghia vu tiem tang", "nghia vu hoan nguyen", "cam ket thanh toan",
            "cam ket thue", "cam ket dau tu"))
    if topic == "related_parties":
        return (any(phrase in normalized for phrase in
                    ("ben lien quan", "quan ly chu chot", "cong ty lien doanh")) and
                any(phrase in normalized for phrase in
                    ("phat sinh giao dich", "khong co cong no", "so du phai thu",
                     "so du phai tra", "doanh thu cung cap dich vu")))
    if topic == "subsequent_events" and any(phrase in normalized for phrase in (
            "chuan muc ke toan", "chinh sach ke toan", "ghi giam doanh thu")):
        return False
    if topic == "subsequent_events" and \
            "khong co su kien bat thuong nao xay ra sau ngay" in normalized:
        return True
    return any(phrase in normalized for phrase in phrases)


def excerpt_span(task, text: str) -> tuple[int, int] | None:
    """Return an exact source span; headings, tables and long passages are skipped."""
    for paragraph in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        candidates = [paragraph.span()]
        if len(paragraph.group()) > 650:
            candidates = []
            for sentence in re.finditer(r"[^.!?\n]+[.!?]?", paragraph.group()):
                candidates.append((paragraph.start() + sentence.start(),
                                   paragraph.start() + sentence.end()))
        for start, end in candidates:
            if text[start] == "[" and "|" in text[start:text.find("\n", start, end)]:
                first_newline = text.find("\n", start, end)
                if first_newline >= 0:
                    start = first_newline + 1
            while "\n" in text[start:end]:
                first_line, _, _ = text[start:end].partition("\n")
                if len(first_line) > 80 or not (
                        first_line.rstrip().endswith(":") or
                        re.match(r"^\s*\d+[.]", first_line)):
                    break
                start += len(first_line) + 1
            heading = re.search(r"\s+\d{1,2}\.\d{1,2}\s+[A-ZÀ-Ỹ]", text[start:end])
            if heading is not None and heading.start() >= 70:
                end = start + heading.start()
            passage = text[start:end].strip()
            if not (70 <= len(passage) <= 650) or passage.count("|") >= 2:
                continue
            if re.match(r"^\d+[.]\s", passage):
                continue
            if re.match(r"^\(\s*\*", passage):
                continue
            if len(passage.split()) < 12 or passage.endswith(":"):
                continue
            if not _matches_topic(task, passage):
                continue
            start += len(text[start:end]) - len(text[start:end].lstrip())
            end -= len(text[start:end]) - len(text[start:end].rstrip())
            return start, end
    return None
