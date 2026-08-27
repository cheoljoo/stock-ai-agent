#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""회사명에 대한 AI 종합 분석 결과를 Telegram으로 전송한다.

사용법:
    uv run python notify_telegram_analysis.py "알파벳A"
    uv run python notify_telegram_analysis.py  # 인자 생략 시 기본값 "알파벳A"
"""

import sys

from strands import Agent
from stock_sim.telegram import TelegramNotifier

from ai_backend import create_agent_model
from stock_agent import analyze_company_news, analyze_stock_trend, get_stock_price


def build_analysis(company_name: str) -> str:
    price = get_stock_price(company_name)
    trend = analyze_stock_trend(company_name)
    news = analyze_company_news(company_name)

    data_summary = f"""**현재 주가 정보:**
{price}

**기술적 분석 (RSI, MACD, 이동평균, 볼린저밴드 등):**
{trend}

**뉴스 감성 분석:**
{news}
"""

    agent = Agent(
        model=create_agent_model(),
        tools=[],
        callback_handler=None,  # 콘솔에 토큰 스트리밍을 출력하지 않음(조용히 실행)
        system_prompt=(
            "당신은 주식 정보 도우미입니다. 아래 데이터를 종합해 매수/매도/관망 신호와 "
            "핵심 근거를 한국어로 간결하게 정리하세요. Telegram 메시지로 보낼 것이므로 "
            "과도한 마크다운 서식은 피하고 이모지와 짧은 문단 위주로 작성하세요.\n\n"
            + data_summary
        ),
    )
    result = agent(f"{company_name}에 대한 종합 분석을 알려줘.")
    return str(result)


def main() -> None:
    company_name = sys.argv[1] if len(sys.argv) > 1 else "알파벳A"

    analysis_text = build_analysis(company_name)
    message = f"📊 {company_name} AI 종합 분석\n\n{analysis_text}"

    notifier = TelegramNotifier.from_env()
    notifier.send_message(message, parse_mode="")
    print("Telegram 전송 완료")


if __name__ == "__main__":
    main()
