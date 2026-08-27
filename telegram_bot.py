#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""승인된 사용자만 AI 주식 분석을 받을 수 있는 Telegram 봇 리스너.

동작 방식:
    1. 누군가 봇(예: https://t.me/news_charles_bot)에게 메시지를 보내면
       stock_sim.telegram.TelegramBotListener가 이를 받아온다.
    2. 보낸 사람의 chat_id가 승인 목록(stock_sim.telegram.ChatAllowlist:
       TELEGRAM_CHAT_ID 또는 TELEGRAM_APPROVED_CHAT_IDS)에 없으면:
       - 요청자에게 "승인 대기 중" 안내와 자신의 chat_id를 알려준다.
       - 관리자(TELEGRAM_CHAT_ID)에게 새 요청이 왔다고 1회 알린다.
    3. 승인된 사용자가 종목명을 보내면 AI 종합 분석을 만들어 답장한다.

승인 방법:
    .env의 TELEGRAM_APPROVED_CHAT_IDS에 chat_id를 콤마로 추가하면 된다.
    이 봇은 매 폴링마다 .env를 다시 읽으므로 재시작 없이 즉시 반영된다.

사용법:
    uv run python telegram_bot.py
"""

import os

from dotenv import load_dotenv
from stock_sim.telegram import ChatAllowlist, TelegramBotListener, TelegramNotifier

from notify_telegram_analysis import build_analysis

OFFSET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".telegram_bot_offset")


def handle_message(allowlist: ChatAllowlist, bot_token: str, message: dict) -> None:
    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))
    text = (message.get("text") or "").strip()
    username = chat.get("username") or chat.get("first_name") or "알 수 없음"

    if not allowlist.is_approved(chat_id):
        TelegramNotifier(bot_token, chat_id).send_message(
            f"🔒 승인 대기 중입니다.\n회원님의 chat ID: {chat_id}\n"
            "이 ID를 관리자에게 전달해 승인을 요청하세요.",
            parse_mode="",
        )
        admin_chat_id = allowlist.admin_chat_id()
        if admin_chat_id and allowlist.should_notify_admin(chat_id):
            TelegramNotifier(bot_token, admin_chat_id).send_message(
                f"🔔 새로운 사용자가 봇을 시작했습니다.\n"
                f"chat_id={chat_id} (username: {username})\n"
                "승인하려면 .env의 TELEGRAM_APPROVED_CHAT_IDS에 이 chat_id를 추가하세요.",
                parse_mode="",
            )
        return

    notifier = TelegramNotifier(bot_token, chat_id)
    if not text or text.startswith("/start"):
        notifier.send_message("📈 분석을 원하는 종목명을 보내주세요. 예: 삼성전자, 알파벳A, TSLA", parse_mode="")
        return

    notifier.send_message(f"⏳ {text} 분석 중입니다... (최대 1~2분 소요)", parse_mode="")
    try:
        analysis_text = build_analysis(text)
        notifier.send_message(f"📊 {text} AI 종합 분석\n\n{analysis_text}", parse_mode="")
    except Exception as e:
        notifier.send_message(f"❌ 분석 중 오류가 발생했습니다: {e}", parse_mode="")


def main() -> None:
    load_dotenv()
    listener = TelegramBotListener.from_env(offset_file=OFFSET_FILE)
    allowlist = ChatAllowlist()

    print("Telegram bot polling 시작...")
    listener.run_forever(lambda message: handle_message(allowlist, listener.bot_token, message))


if __name__ == "__main__":
    main()
