#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KOSPI 시가총액 상위 20 + S&P500 시가총액 상위 50 종목 중 1개를 무작위로 골라
AI 종합 분석을 만들고 Telegram으로 전송한다.

매일 오전 7시(KST) systemd 타이머(deploy/daily-random-analysis.timer)로 실행된다.

사용법:
    uv run python daily_random_analysis.py
"""

import random

from notify_telegram_analysis import broadcast_analysis

KOSPI_TOP20 = [
    "삼성전자", "SK하이닉스", "LG에너지솔루션", "삼성바이오로직스", "현대차",
    "기아", "셀트리온", "네이버", "POSCO홀딩스", "삼성SDI",
    "LG화학", "KB금융", "신한지주", "삼성물산", "현대모비스",
    "카카오", "하나금융지주", "LG전자", "SK이노베이션", "한화에어로스페이스",
]

SP500_TOP50 = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "LLY", "JPM",
    "WMT", "V", "UNH", "XOM", "MA", "ORCL", "PG", "JNJ", "HD", "COST",
    "ABBV", "NFLX", "BAC", "KO", "CRM", "CVX", "MRK", "AMD", "PEP", "TMO",
    "ADBE", "LIN", "ACN", "MCD", "CSCO", "ABT", "WFC", "GE", "IBM", "PM",
    "CAT", "DHR", "TXN", "INTU", "VZ", "DIS", "AMAT", "NOW", "QCOM", "GS",
]

STOCK_POOL = KOSPI_TOP20 + SP500_TOP50


def main() -> None:
    company_name = random.choice(STOCK_POOL)
    print(f"오늘의 랜덤 종목: {company_name}")
    broadcast_analysis(company_name, title_prefix="🎲 오늘의 랜덤 분석")


if __name__ == "__main__":
    main()
