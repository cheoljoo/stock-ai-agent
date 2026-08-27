#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주식 정보 AI Agent - 백엔드 도구 모듈

이 모듈은 AI 에이전트가 사용하는 도구(Tool)들을 정의합니다.
각 도구는 @tool 데코레이터로 정의되며, AI가 자동으로 호출할 수 있습니다.

제공 기능:
- 실시간 주가 조회 (한국/미국 주식)
- 기술적 분석 (이동평균, RSI, MACD, 볼린저밴드)
- 기본적 분석 (밸류에이션, 수익성, 재무건전성)
- 기관/내부자 보유 현황
- 동종업계 비교 분석
- 거시경제 지표
- 뉴스 감성 분석 (NLP 기반)

사용 기술:
- yfinance: 야후 파이낸스 API (주가, 재무 데이터)
- feedparser: RSS 뉴스 피드 파싱
- Strands Agent SDK: AI 에이전트 프레임워크
- agy CLI: 로컬 계정(Google/Anthropic) 기반 AI 모델 호출
"""

# =============================================================================
# 라이브러리 임포트
# =============================================================================
import sys                        # 시스템 설정 (인코딩)
import os                         # 운영체제 인터페이스
import yfinance as yf             # 야후 파이낸스 API
import pandas as pd               # 데이터 처리
import numpy as np                # 수치 연산
import feedparser                 # RSS 피드 파싱
from datetime import datetime, timedelta  # 날짜/시간 처리
from strands import Agent, tool   # AI 에이전트 및 도구 데코레이터
from ai_backend import create_agent_model   # 로컬 계정 기반 AI 모델(agy CLI)
from prophet import Prophet       # 시계열 예측 모델

# =============================================================================
# UTF-8 인코딩 설정
# Windows 환경에서 한글 출력을 위한 설정
# =============================================================================
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stdin.encoding != 'utf-8':
    sys.stdin.reconfigure(encoding='utf-8')

# =============================================================================
# 회사명 → 티커 심볼 매핑 테이블
# 사용자가 입력한 회사명을 yfinance가 인식할 수 있는 티커로 변환
#
# 한국 주식: 6자리 코드 + .KS (예: 005930.KS = 삼성전자)
# 미국 주식: 영문 티커 심볼 (예: AAPL = 애플)
# =============================================================================
TICKER_MAP = {
    # 미국 주식 (영문/한글 모두 지원)
    "amazon": "AMZN", "아마존": "AMZN",
    "apple": "AAPL", "애플": "AAPL",
    "tesla": "TSLA", "테슬라": "TSLA",
    "google": "GOOGL", "구글": "GOOGL",
    "alphabet": "GOOGL", "alphabeta": "GOOGL", "알파벳": "GOOGL", "알파벳a": "GOOGL", "알파벳A": "GOOGL",
    "microsoft": "MSFT", "마이크로소프트": "MSFT",
    "meta": "META", "메타": "META",
    "nvidia": "NVDA", "엔비디아": "NVDA",
    # 한국 주식 (종목코드.KS 형식)
    "삼성전자": "005930.KS",
    "sk하이닉스": "000660.KS", "SK하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "네이버": "035420.KS",
    "카카오": "035720.KS",
    "현대차": "005380.KS", "현대자동차": "005380.KS",
    "lg전자": "066570.KS", "LG전자": "066570.KS",
    "포스코": "005490.KS",
    # 한국 주식 - KOSPI 시가총액 상위 추가 종목
    "lg에너지솔루션": "373220.KS", "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
    "기아": "000270.KS",
    "셀트리온": "068270.KS",
    "posco홀딩스": "005490.KS", "POSCO홀딩스": "005490.KS",
    "삼성sdi": "006400.KS", "삼성SDI": "006400.KS",
    "lg화학": "051910.KS", "LG화학": "051910.KS",
    "kb금융": "105560.KS", "KB금융": "105560.KS",
    "신한지주": "055550.KS",
    "삼성물산": "028260.KS",
    "현대모비스": "012330.KS",
    "하나금융지주": "086790.KS",
    "sk이노베이션": "096770.KS", "SK이노베이션": "096770.KS",
    "한화에어로스페이스": "012450.KS"
}


def get_ticker(company_name: str) -> str:
    """회사명을 티커 심볼로 변환
    
    Args:
        company_name: 회사명 (예: "삼성전자", "SK 하이닉스", "Amazon")
    
    Returns:
        티커 심볼 (예: "005930.KS", "AMZN")
    
    처리 로직:
    1. 공백 제거 ("SK 하이닉스" → "SK하이닉스")
    2. TICKER_MAP에서 검색
    3. 없으면 6자리 숫자는 .KS 추가
    4. 그 외는 대문자로 변환
    """
    # 공백 제거
    cleaned_name = company_name.replace(" ", "")
    # 영문은 소문자로, 한글은 그대로
    search_key = cleaned_name.lower() if cleaned_name.isascii() else cleaned_name
    # 티커 매핑에서 검색
    ticker = TICKER_MAP.get(search_key)
    
    if not ticker:
        # 6자리 숫자는 한국 주식 코드로 간주
        if company_name.isdigit() and len(company_name) == 6:
            ticker = f"{company_name}.KS"
        else:
            # 그 외는 대문자로 변환 (직접 티커 입력 가능)
            ticker = company_name.upper()
    
    return ticker


# =============================================================================
# 도구 1: 기술적 분석 (Technical Analysis)
# =============================================================================
@tool
def analyze_stock_trend(company_name: str, period: str = "3mo") -> dict:
    """주가 추이를 분석하여 투자 판단에 도움이 되는 데이터를 제공합니다.

    기술적 분석 지표:
    - 이동평균선 (MA5, MA20, MA60)
    - RSI (상대강도지수) - 과매수/과매도 판단
    - MACD (추세 전환 신호)
    - 볼린저밴드 (변동성 범위)
    - 골든크로스/데드크로스 (매수/매도 신호)

    Args:
        company_name: 회사명을 정확히 입력하세요.
                     예시: "삼성전자", "005930", "Amazon"
                     주의: 영어로 번역하지 말고 사용자가 입력한 그대로 전달하세요.
        period: 분석 기간 ("1mo", "3mo", "6mo", "1y") 기본값 3개월

    Returns:
        주가 분석 데이터 (이동평균, RSI, 변동성 등)
    """
    # 회사명을 티커 심볼로 변환
    ticker = get_ticker(company_name)

    # yfinance API로 주가 데이터 조회
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)  # OHLCV 데이터
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}
    
    # 데이터가 없으면 에러 반환
    if df.empty:
        return {"error": f"{company_name}의 데이터를 가져올 수 없습니다. 한국 주식의 경우 6자리 종목코드를 입력해주세요."}
    
    # 현재가
    current_price = df['Close'].iloc[-1]
    
    # 이동평균선 계산 (5일, 20일, 60일)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    ma5 = df['MA5'].iloc[-1] if len(df) >= 5 else None
    ma20 = df['MA20'].iloc[-1] if len(df) >= 20 else None
    ma60 = df['MA60'].iloc[-1] if len(df) >= 60 else None
    
    # RSI 계산 (14일) - 0으로 나누기 방지
    delta = df['Close'].diff()  # 전일 대비 변화량
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()  # 상승분 평균
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()  # 하락분 평균
    
    # loss가 0인 경우 처리 (0으로 나누기 방지)
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if len(df) >= 14 and not pd.isna(rsi.iloc[-1]) else None
    
    # 변동성 계산 (최근 30일 고가-저가 범위)
    recent_30d = df.tail(30)
    if len(recent_30d) > 0 and recent_30d['Low'].min() > 0:
        volatility = ((recent_30d['High'].max() - recent_30d['Low'].min()) / recent_30d['Low'].min()) * 100
    else:
        volatility = 0
    
    # 거래량 추이 (최근 거래량 vs 20일 평균)
    avg_volume = df['Volume'].tail(20).mean()
    recent_volume = df['Volume'].iloc[-1]
    volume_ratio = (recent_volume / avg_volume) * 100 if avg_volume > 0 else 0
    
    # 기간 수익률 (시작가 대비 현재가) - ZeroDivision 방지
    start_price = df['Close'].iloc[0]
    period_return = ((current_price - start_price) / start_price) * 100 if start_price > 0 else 0
    
    # MACD (Moving Average Convergence Divergence) - 추세 전환 신호
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()  # 12일 지수이동평균
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()  # 26일 지수이동평균
    macd = exp12 - exp26  # MACD 선
    signal = macd.ewm(span=9, adjust=False).mean()  # 시그널 선
    macd_histogram = macd - signal  # 히스토그램 (MACD - Signal)
    
    # 볼린저 밴드 (20일 기준, 2 표준편차)
    bb_middle = df['Close'].rolling(window=20).mean()  # 중심선 (20일 이동평균)
    bb_std = df['Close'].rolling(window=20).std()  # 표준편차
    bb_upper = bb_middle + (bb_std * 2)  # 상단 밴드
    bb_lower = bb_middle - (bb_std * 2)  # 하단 밴드
    
    # 현재가의 볼린저 밴드 위치 (%) - 0%=하단, 100%=상단 - ZeroDivision 방지
    if len(df) >= 20:
        bb_width = bb_upper.iloc[-1] - bb_lower.iloc[-1]
        bb_position = ((current_price - bb_lower.iloc[-1]) / bb_width) * 100 if bb_width > 0 else 50
    else:
        bb_position = None
    
    # 골든크로스/데드크로스 확인 (MA5와 MA20 교차)
    cross_signal = None
    if ma5 and ma20 and len(df) >= 21:
        prev_ma5 = df['MA5'].iloc[-2]
        prev_ma20 = df['MA20'].iloc[-2]
        # 골든크로스: 단기 이평선이 장기 이평선을 상향 돌파 (매수 신호)
        if prev_ma5 <= prev_ma20 and ma5 > ma20:
            cross_signal = "골든크로스"
        # 데드크로스: 단기 이평선이 장기 이평선을 하향 돌파 (매도 신호)
        elif prev_ma5 >= prev_ma20 and ma5 < ma20:
            cross_signal = "데드크로스"
    
    # 분석 결과 반환
    return {
        "company": company_name,
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "period": period,
        "period_return": round(period_return, 2),  # 기간 수익률
        "ma5": round(ma5, 2) if ma5 else None,  # 5일 이동평균
        "ma20": round(ma20, 2) if ma20 else None,  # 20일 이동평균
        "ma60": round(ma60, 2) if ma60 else None,  # 60일 이동평균
        "rsi": round(current_rsi, 2) if current_rsi else None,  # RSI (과매수/과매도)
        "macd": round(macd.iloc[-1], 2) if len(df) >= 26 else None,  # MACD 선
        "macd_signal": round(signal.iloc[-1], 2) if len(df) >= 26 else None,  # 시그널 선
        "macd_histogram": round(macd_histogram.iloc[-1], 2) if len(df) >= 26 else None,  # 히스토그램
        "bb_position": round(bb_position, 2) if bb_position else None,  # 볼린저밴드 위치 (%)
        "cross_signal": cross_signal,  # 골든크로스/데드크로스
        "volatility": round(volatility, 2),  # 변동성
        "volume_ratio": round(volume_ratio, 2),  # 거래량 비율
        "highest": round(df['High'].max(), 2),  # 기간 최고가
        "lowest": round(df['Low'].min(), 2)  # 기간 최저가
    }


# =============================================================================
# 뉴스 감성 분석 헬퍼 함수 (NLP 기반)
# =============================================================================
def analyze_sentiment(text: str) -> dict:
    """뉴스 제목의 감성을 분석하여 점수화합니다.

    키워드 기반 감성 분석:
    - 긍정 키워드: surge, soar, beat, rise, gain, rally, upgrade 등
    - 부정 키워드: crash, plunge, fall, drop, decline, downgrade 등
    - 각 키워드에 가중치를 부여하여 점수 계산

    Args:
        text: 분석할 텍스트 (뉴스 제목)

    Returns:
        감성 점수 (-100 ~ +100), 감성 라벨, 키워드
    """
    text_lower = text.lower()

    # -------------------------------------------------------------------------
    # 긍정 키워드 사전 (가중치 포함)
    # 강한 긍정: +15, 중간 긍정: +10, 약한 긍정: +5
    # -------------------------------------------------------------------------
    positive_keywords = {
        # 강한 긍정 (+15) - 급등, 신기록 등
        "surge": 15, "soar": 15, "skyrocket": 15, "breakthrough": 15, "record high": 15,
        "beat": 12, "beats": 12, "exceed": 12, "exceeds": 12, "outperform": 12,
        # 중간 긍정 (+10) - 상승, 성장 등
        "rise": 10, "rises": 10, "gain": 10, "gains": 10, "jump": 10, "jumps": 10,
        "rally": 10, "rallies": 10, "climb": 10, "climbs": 10, "boost": 10,
        "upgrade": 10, "upgrades": 10, "bullish": 10, "growth": 10, "profit": 10,
        # 약한 긍정 (+5) - 일반 긍정 표현
        "up": 5, "higher": 5, "positive": 5, "strong": 5, "buy": 5,
        "recover": 5, "recovery": 5, "improve": 5, "expansion": 5, "deal": 5,
        "partnership": 5, "innovation": 5, "launch": 5, "success": 5, "win": 5
    }

    # -------------------------------------------------------------------------
    # 부정 키워드 사전 (가중치 포함)
    # 강한 부정: -15, 중간 부정: -10, 약한 부정: -5
    # -------------------------------------------------------------------------
    negative_keywords = {
        # 강한 부정 (-15) - 폭락, 스캔들 등
        "crash": -15, "plunge": -15, "collapse": -15, "scandal": -15, "fraud": -15,
        "bankruptcy": -15, "lawsuit": -15, "investigation": -15,
        # 중간 부정 (-10) - 하락, 손실 등
        "fall": -10, "falls": -10, "drop": -10, "drops": -10, "decline": -10,
        "declines": -10, "tumble": -10, "sink": -10, "sinks": -10, "slump": -10,
        "downgrade": -10, "downgrades": -10, "bearish": -10, "loss": -10, "losses": -10,
        # 약한 부정 (-5) - 일반 부정 표현
        "down": -5, "lower": -5, "negative": -5, "weak": -5, "sell": -5,
        "concern": -5, "concerns": -5, "risk": -5, "risks": -5, "warning": -5,
        "cut": -5, "cuts": -5, "layoff": -5, "layoffs": -5, "miss": -5, "misses": -5
    }

    score = 0
    found_positive = []
    found_negative = []

    # 키워드 매칭 및 점수 계산
    for keyword, weight in positive_keywords.items():
        if keyword in text_lower:
            score += weight
            found_positive.append(keyword)

    for keyword, weight in negative_keywords.items():
        if keyword in text_lower:
            score += weight  # weight는 이미 음수
            found_negative.append(keyword)

    # 점수 범위 제한 (-100 ~ +100)
    score = max(-100, min(100, score))

    # 감성 라벨 결정
    if score >= 20:
        label = "매우 긍정"
    elif score >= 5:
        label = "긍정"
    elif score <= -20:
        label = "매우 부정"
    elif score <= -5:
        label = "부정"
    else:
        label = "중립"

    return {
        "score": score,
        "label": label,
        "positive_keywords": found_positive,
        "negative_keywords": found_negative
    }


# =============================================================================
# 도구 2: 뉴스 감성 분석 (News Sentiment Analysis)
# =============================================================================
@tool
def analyze_company_news(company_name: str) -> dict:
    """회사 관련 최근 뉴스를 수집하고 NLP 기반 감성을 분석합니다.

    Google News RSS 피드를 통해 최근 뉴스를 수집하고,
    키워드 기반 감성 분석으로 각 기사의 긍정/부정을 점수화합니다.

    Args:
        company_name: 회사명을 정확히 입력하세요.
                     예시: "삼성전자", "Amazon"
                     주의: 영어로 번역하지 말고 사용자가 입력한 그대로 전달하세요.

    Returns:
        최근 뉴스 목록, 개별 감성 점수, 종합 감성 점수
    """
    from urllib.parse import quote  # URL 인코딩용

    # 영문 회사명 매핑 (Google News 검색용)
    english_name_map = {
        "삼성전자": "Samsung Electronics", "삼성 전자": "Samsung Electronics",
        "sk하이닉스": "SK Hynix", "하이닉스": "SK Hynix", "sk 하이닉스": "SK Hynix",
        "네이버": "Naver",
        "카카오": "Kakao",
        "현대차": "Hyundai Motor", "현대자동차": "Hyundai Motor", "현대 차": "Hyundai Motor",
        "lg전자": "LG Electronics", "lg 전자": "LG Electronics",
        "포스코": "POSCO",
        "아마존": "Amazon",
        "애플": "Apple",
        "테슬라": "Tesla",
        "구글": "Google",
        "마이크로소프트": "Microsoft",
        "메타": "Meta",
        "엔비디아": "Nvidia"
    }

    search_key = company_name.replace(" ", "")
    search_name = english_name_map.get(search_key, company_name)

    encoded_query = quote(f"{search_name} stock")
    news_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(news_url)

        if not feed.entries:
            return {
                "company": company_name,
                "news_count": 0,
                "news": [],
                "overall_sentiment": {"score": 0, "label": "중립"},
                "error": "뉴스를 찾을 수 없습니다."
            }

        # 최근 5개 뉴스 수집 및 감성 분석
        news_list = []
        total_score = 0

        for entry in feed.entries[:5]:
            sentiment = analyze_sentiment(entry.title)
            total_score += sentiment["score"]

            news_list.append({
                "title": entry.title,
                "published": entry.get('published', 'N/A'),
                "link": entry.link,
                "sentiment_score": sentiment["score"],
                "sentiment_label": sentiment["label"],
                "positive_keywords": sentiment["positive_keywords"],
                "negative_keywords": sentiment["negative_keywords"]
            })

        # 종합 감성 점수 계산 (평균)
        avg_score = total_score / len(news_list) if news_list else 0

        # 종합 감성 라벨
        if avg_score >= 15:
            overall_label = "매우 긍정"
        elif avg_score >= 5:
            overall_label = "긍정"
        elif avg_score <= -15:
            overall_label = "매우 부정"
        elif avg_score <= -5:
            overall_label = "부정"
        else:
            overall_label = "중립"

        # 긍정/부정 뉴스 개수
        positive_count = sum(1 for n in news_list if n["sentiment_score"] > 0)
        negative_count = sum(1 for n in news_list if n["sentiment_score"] < 0)
        neutral_count = len(news_list) - positive_count - negative_count

        return {
            "company": company_name,
            "search_name": search_name,
            "news_count": len(news_list),
            "news": news_list,
            "overall_sentiment": {
                "score": round(avg_score, 1),
                "label": overall_label,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "neutral_count": neutral_count
            }
        }

    except Exception as e:
        return {
            "company": company_name,
            "error": f"뉴스 수집 중 오류 발생: {str(e)}"
        }


# =============================================================================
# 도구 3: 현재가 조회 (Current Price)
# =============================================================================
@tool
def get_stock_price(company_name: str) -> dict:
    """주식 현재가 및 변동 정보를 조회합니다.

    현재가, 전일 종가, 변동률을 반환합니다.

    Args:
        company_name: 회사명을 정확히 입력하세요.
                     예시: "삼성전자", "네이버", "Amazon", "Apple"
                     주의: 영어로 번역하지 말고 사용자가 입력한 그대로 전달하세요.

    Returns:
        주가 정보를 담은 딕셔너리 (current_price, previous_price, change_percent)
    """
    # 회사명을 티커 심볼로 변환
    ticker = get_ticker(company_name)

    # yfinance로 최근 2일 주가 데이터 조회 (현재가와 전일가 비교용)
    try:
        stock = yf.Ticker(ticker)
        info = stock.history(period="2d")
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}
    
    # 데이터가 없으면 에러 반환
    if info.empty:
        return {"error": f"{company_name}의 주가 정보를 찾을 수 없습니다. 한국 주식의 경우 6자리 종목코드(예: 051910)를 입력하거나, 주요 기업명(삼성전자, 네이버, 카카오 등)을 입력해주세요."}
    
    # 현재가 (가장 최근 종가)
    current_price = info['Close'].iloc[-1]
    # 전일 종가
    previous_price = info['Close'].iloc[-2] if len(info) > 1 else current_price
    
    # 변동률 계산 (0으로 나누기 방지)
    if previous_price > 0:
        change_percent = ((current_price - previous_price) / previous_price) * 100
    else:
        change_percent = 0
    
    return {
        "company": company_name,
        "ticker": ticker,
        "current_price": round(current_price, 2),  # 현재가
        "previous_price": round(previous_price, 2),  # 전일 종가
        "change_percent": round(change_percent, 2)  # 변동률 (%)
    }


# =============================================================================
# 도구 4: 기본적 분석 (Fundamental Analysis)
# =============================================================================
@tool
def get_fundamental_analysis(company_name: str) -> dict:
    """기업의 기본적 분석(펀더멘털) 데이터를 조회합니다.

    포함 지표:
    - 밸류에이션: P/E, P/B, PEG, PSR
    - 수익성: ROE, ROA, 영업이익률, 순이익률
    - 재무건전성: 부채비율, 유동비율, 당좌비율
    - 성장성: 매출성장률, 이익성장률

    Args:
        company_name: 회사명을 정확히 입력하세요.
                     예시: "삼성전자", "Amazon", "Apple"
                     주의: 영어로 번역하지 말고 사용자가 입력한 그대로 전달하세요.

    Returns:
        밸류에이션, 수익성, 재무건전성, 성장성 지표
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    if not info:
        return {"error": f"{company_name}의 재무 정보를 찾을 수 없습니다."}

    # 안전하게 값 가져오기 (None 처리)
    def safe_get(key, multiplier=1, decimal=2):
        value = info.get(key)
        if value is not None:
            return round(value * multiplier, decimal)
        return None

    # 밸류에이션 지표
    valuation = {
        "pe_ratio": safe_get('trailingPE'),  # P/E (주가수익비율)
        "forward_pe": safe_get('forwardPE'),  # 예상 P/E
        "pb_ratio": safe_get('priceToBook'),  # P/B (주가순자산비율)
        "peg_ratio": safe_get('pegRatio'),  # PEG (주가수익성장비율)
        "ps_ratio": safe_get('priceToSalesTrailing12Months'),  # PSR (주가매출비율)
    }

    # 수익성 지표
    profitability = {
        "roe": safe_get('returnOnEquity', 100),  # ROE (자기자본이익률) %
        "roa": safe_get('returnOnAssets', 100),  # ROA (총자산이익률) %
        "operating_margin": safe_get('operatingMargins', 100),  # 영업이익률 %
        "profit_margin": safe_get('profitMargins', 100),  # 순이익률 %
        "gross_margin": safe_get('grossMargins', 100),  # 매출총이익률 %
    }

    # 재무건전성 지표
    financial_health = {
        "debt_to_equity": safe_get('debtToEquity'),  # 부채비율
        "current_ratio": safe_get('currentRatio'),  # 유동비율
        "quick_ratio": safe_get('quickRatio'),  # 당좌비율
    }

    # 성장성 지표
    growth = {
        "revenue_growth": safe_get('revenueGrowth', 100),  # 매출 성장률 %
        "earnings_growth": safe_get('earningsGrowth', 100),  # 이익 성장률 %
    }

    # 기타 정보
    other = {
        "market_cap": info.get('marketCap'),  # 시가총액
        "enterprise_value": info.get('enterpriseValue'),  # 기업가치
        "dividend_yield": safe_get('dividendYield', 100),  # 배당수익률 %
        "dividend_rate": info.get('dividendRate'),  # 배당금
        "beta": safe_get('beta'),  # 베타 (시장 대비 변동성)
        "fifty_two_week_high": safe_get('fiftyTwoWeekHigh'),  # 52주 최고가
        "fifty_two_week_low": safe_get('fiftyTwoWeekLow'),  # 52주 최저가
        "eps": safe_get('trailingEps'),  # 주당순이익
        "book_value": safe_get('bookValue'),  # 주당순자산
    }

    return {
        "company": company_name,
        "ticker": ticker,
        "valuation": valuation,
        "profitability": profitability,
        "financial_health": financial_health,
        "growth": growth,
        "other": other
    }


# =============================================================================
# 도구 5: 기관/내부자 보유 현황 (Institutional Holdings)
# =============================================================================
@tool
def get_institutional_holders(company_name: str) -> dict:
    """기관 및 주요 투자자 보유 현황을 조회합니다.

    포함 정보:
    - 기관투자자 보유비율
    - 내부자(경영진) 보유비율
    - 주요 기관투자자 목록 (상위 5개)
    - 주요 펀드 보유 목록 (상위 5개)

    Args:
        company_name: 회사명을 정확히 입력하세요.
                     예시: "삼성전자", "Amazon", "Apple"
                     주의: 영어로 번역하지 말고 사용자가 입력한 그대로 전달하세요.

    Returns:
        기관투자자 보유비율, 주요 주주 목록
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    # 기관/내부자 보유비율
    institutional_percent = info.get('heldPercentInstitutions')
    insider_percent = info.get('heldPercentInsiders')

    # 주요 기관투자자 목록
    top_institutions = []
    try:
        holders = stock.institutional_holders
        if holders is not None and not holders.empty:
            for _, row in holders.head(5).iterrows():
                top_institutions.append({
                    "holder": row.get('Holder', 'N/A'),
                    "shares": int(row.get('Shares', 0)) if pd.notna(row.get('Shares')) else 0,
                    "value": int(row.get('Value', 0)) if pd.notna(row.get('Value')) else 0,
                    "percent": round(row.get('pctHeld', 0) * 100, 2) if pd.notna(row.get('pctHeld')) else None
                })
    except Exception:
        pass  # 기관투자자 데이터가 없는 경우

    # 주요 펀드 보유 목록
    top_funds = []
    try:
        funds = stock.mutualfund_holders
        if funds is not None and not funds.empty:
            for _, row in funds.head(5).iterrows():
                top_funds.append({
                    "holder": row.get('Holder', 'N/A'),
                    "shares": int(row.get('Shares', 0)) if pd.notna(row.get('Shares')) else 0,
                    "value": int(row.get('Value', 0)) if pd.notna(row.get('Value')) else 0,
                    "percent": round(row.get('pctHeld', 0) * 100, 2) if pd.notna(row.get('pctHeld')) else None
                })
    except Exception:
        pass  # 펀드 데이터가 없는 경우

    return {
        "company": company_name,
        "ticker": ticker,
        "institutional_percent": round(institutional_percent * 100, 2) if institutional_percent else None,
        "insider_percent": round(insider_percent * 100, 2) if insider_percent else None,
        "top_institutions": top_institutions,
        "top_funds": top_funds,
        "float_shares": info.get('floatShares'),  # 유통주식수
        "shares_outstanding": info.get('sharesOutstanding'),  # 발행주식수
    }


# =============================================================================
# 도구 6: 동종업계 비교 분석 (Peer Comparison)
# =============================================================================
@tool
def get_peer_comparison(company_name: str) -> dict:
    """동종업계 경쟁사와 주요 지표를 비교 분석합니다.

    비교 지표:
    - 밸류에이션: P/E, P/B, PSR
    - 수익성: ROE, 순이익률
    - 성장성: 매출성장률

    상대 평가:
    - 업종 평균 대비 저평가/고평가 판단
    - 업종 평균 대비 수익성/성장성 평가

    Args:
        company_name: 회사명을 정확히 입력하세요.
                     예시: "삼성전자", "Amazon", "Apple"
                     주의: 영어로 번역하지 말고 사용자가 입력한 그대로 전달하세요.

    Returns:
        동종업계 비교 데이터 (섹터, 업종, 경쟁사 지표 비교)
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    # 섹터/업종 정보
    sector = info.get('sector', 'N/A')
    industry = info.get('industry', 'N/A')

    # 업종별 대표 경쟁사 매핑
    industry_peers = {
        # 반도체
        "Semiconductors": ["NVDA", "AMD", "INTC", "TSM", "AVGO"],
        "Semiconductor Equipment & Materials": ["ASML", "AMAT", "LRCX", "KLAC"],
        # 테크
        "Consumer Electronics": ["AAPL", "005930.KS", "SONY", "066570.KS"],
        "Internet Content & Information": ["GOOGL", "META", "035420.KS", "035720.KS"],
        "Software - Infrastructure": ["MSFT", "ORCL", "CRM", "NOW"],
        # 자동차
        "Auto Manufacturers": ["TSLA", "TM", "F", "GM", "005380.KS"],
        # 이커머스/리테일
        "Internet Retail": ["AMZN", "BABA", "JD", "EBAY"],
        # 기타 테크
        "Information Technology Services": ["IBM", "ACN", "INFY"],
    }

    # 현재 회사의 업종에 맞는 경쟁사 선택
    peer_tickers = industry_peers.get(industry, [])

    # 경쟁사가 없으면 같은 섹터의 대표 기업들 사용
    if not peer_tickers:
        sector_defaults = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
            "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE"],
            "Communication Services": ["GOOGL", "META", "NFLX", "DIS"],
            "Financial Services": ["JPM", "BAC", "GS", "MS"],
            "Healthcare": ["JNJ", "UNH", "PFE", "ABBV"],
        }
        peer_tickers = sector_defaults.get(sector, [])

    # 현재 회사가 리스트에 있으면 제거
    peer_tickers = [t for t in peer_tickers if t != ticker][:4]  # 최대 4개 경쟁사

    # 현재 회사 데이터 수집
    def safe_get(data, key, multiplier=1, decimal=2):
        value = data.get(key)
        if value is not None:
            return round(value * multiplier, decimal)
        return None

    company_data = {
        "ticker": ticker,
        "name": company_name,
        "pe_ratio": safe_get(info, 'trailingPE'),
        "pb_ratio": safe_get(info, 'priceToBook'),
        "ps_ratio": safe_get(info, 'priceToSalesTrailing12Months'),
        "roe": safe_get(info, 'returnOnEquity', 100),
        "profit_margin": safe_get(info, 'profitMargins', 100),
        "revenue_growth": safe_get(info, 'revenueGrowth', 100),
        "market_cap": info.get('marketCap'),
        "beta": safe_get(info, 'beta')
    }

    # 경쟁사 데이터 수집
    peers_data = []
    for peer_ticker in peer_tickers:
        try:
            peer_stock = yf.Ticker(peer_ticker)
            peer_info = peer_stock.info
            peer_name = peer_info.get('shortName', peer_ticker)

            peers_data.append({
                "ticker": peer_ticker,
                "name": peer_name,
                "pe_ratio": safe_get(peer_info, 'trailingPE'),
                "pb_ratio": safe_get(peer_info, 'priceToBook'),
                "ps_ratio": safe_get(peer_info, 'priceToSalesTrailing12Months'),
                "roe": safe_get(peer_info, 'returnOnEquity', 100),
                "profit_margin": safe_get(peer_info, 'profitMargins', 100),
                "revenue_growth": safe_get(peer_info, 'revenueGrowth', 100),
                "market_cap": peer_info.get('marketCap'),
                "beta": safe_get(peer_info, 'beta')
            })
        except Exception:
            continue

    # 업종 평균 계산
    def calc_average(key):
        values = [p[key] for p in peers_data if p.get(key) is not None]
        if company_data.get(key) is not None:
            values.append(company_data[key])
        return round(sum(values) / len(values), 2) if values else None

    industry_avg = {
        "pe_ratio": calc_average("pe_ratio"),
        "pb_ratio": calc_average("pb_ratio"),
        "ps_ratio": calc_average("ps_ratio"),
        "roe": calc_average("roe"),
        "profit_margin": calc_average("profit_margin"),
        "revenue_growth": calc_average("revenue_growth")
    }

    # 상대적 위치 평가
    def evaluate_position(company_val, avg_val, metric_type):
        if company_val is None or avg_val is None:
            return "N/A"
        diff_pct = ((company_val - avg_val) / avg_val) * 100 if avg_val != 0 else 0

        # P/E, P/B, P/S는 낮을수록 좋음
        if metric_type in ["pe_ratio", "pb_ratio", "ps_ratio"]:
            if diff_pct <= -20:
                return "매우 저평가"
            elif diff_pct <= -5:
                return "저평가"
            elif diff_pct >= 20:
                return "매우 고평가"
            elif diff_pct >= 5:
                return "고평가"
            else:
                return "적정"
        # ROE, profit_margin, revenue_growth는 높을수록 좋음
        else:
            if diff_pct >= 20:
                return "업종 상위"
            elif diff_pct >= 5:
                return "업종 평균 이상"
            elif diff_pct <= -20:
                return "업종 하위"
            elif diff_pct <= -5:
                return "업종 평균 이하"
            else:
                return "업종 평균"

    relative_position = {
        "pe_ratio": evaluate_position(company_data["pe_ratio"], industry_avg["pe_ratio"], "pe_ratio"),
        "pb_ratio": evaluate_position(company_data["pb_ratio"], industry_avg["pb_ratio"], "pb_ratio"),
        "ps_ratio": evaluate_position(company_data["ps_ratio"], industry_avg["ps_ratio"], "ps_ratio"),
        "roe": evaluate_position(company_data["roe"], industry_avg["roe"], "roe"),
        "profit_margin": evaluate_position(company_data["profit_margin"], industry_avg["profit_margin"], "profit_margin"),
        "revenue_growth": evaluate_position(company_data["revenue_growth"], industry_avg["revenue_growth"], "revenue_growth")
    }

    return {
        "company": company_name,
        "ticker": ticker,
        "sector": sector,
        "industry": industry,
        "company_metrics": company_data,
        "peers": peers_data,
        "industry_average": industry_avg,
        "relative_position": relative_position,
        "peer_count": len(peers_data)
    }


# =============================================================================
# 도구 7: 거시경제 지표 (Macro Indicators)
# =============================================================================
@tool
def get_macro_indicators() -> dict:
    """거시경제 지표를 조회합니다. 시장 전반의 상황을 파악하는데 사용합니다.

    포함 지표:
    - 주요 지수: S&P 500, NASDAQ, Dow Jones, KOSPI, KOSDAQ 등
    - 변동성: VIX (공포지수)
    - 채권/금리: 미국 10년물 국채 금리
    - 환율: USD/KRW, EUR/USD, USD/JPY, 달러인덱스
    - 원자재: 금, 원유, 은, 천연가스

    Returns:
        주요 지수, 변동성, 금리, 환율, 원자재 정보
    """
    import warnings
    warnings.filterwarnings('ignore')  # yfinance 경고 메시지 무시

    result = {
        "indices": {},      # 주요 지수
        "volatility": {},   # 변동성 지표
        "bonds": {},        # 채권/금리
        "currencies": {},   # 환율
        "commodities": {},  # 원자재
        "market_sentiment": None  # 시장 심리
    }

    # 주요 지수 티커
    indices = {
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "Dow Jones": "^DJI",
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "Nikkei 225": "^N225",
        "Shanghai": "000001.SS"
    }

    # 주요 지수 조회
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0
                result["indices"][name] = {
                    "price": round(current, 2),
                    "change_percent": round(change_pct, 2)
                }
        except Exception:
            pass

    # VIX (공포지수)
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        if not vix_hist.empty:
            current_vix = vix_hist['Close'].iloc[-1]
            result["volatility"]["VIX"] = {
                "value": round(current_vix, 2),
                "interpretation": "극심한 공포" if current_vix > 30 else ("공포" if current_vix > 20 else ("중립" if current_vix > 15 else "안정"))
            }
    except Exception:
        pass

    # 미국 국채 금리
    bonds = {
        "US 10Y Treasury": "^TNX",  # 10년물
        "US 2Y Treasury": "^IRX",   # 2년물 (3개월 단기)
    }

    for name, ticker in bonds.items():
        try:
            bond = yf.Ticker(ticker)
            bond_hist = bond.history(period="5d")
            if not bond_hist.empty:
                current = bond_hist['Close'].iloc[-1]
                result["bonds"][name] = {
                    "yield": round(current, 3)
                }
        except Exception:
            pass

    # 환율
    currencies = {
        "USD/KRW": "KRW=X",
        "USD Index (DXY)": "DX-Y.NYB",
        "EUR/USD": "EURUSD=X",
        "USD/JPY": "JPY=X"
    }

    for name, ticker in currencies.items():
        try:
            fx = yf.Ticker(ticker)
            fx_hist = fx.history(period="5d")
            if not fx_hist.empty and len(fx_hist) >= 2:
                current = fx_hist['Close'].iloc[-1]
                prev = fx_hist['Close'].iloc[-2]
                change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0
                result["currencies"][name] = {
                    "rate": round(current, 2),
                    "change_percent": round(change_pct, 2)
                }
        except Exception:
            pass

    # 원자재
    commodities = {
        "Gold": "GC=F",
        "Crude Oil (WTI)": "CL=F",
        "Silver": "SI=F",
        "Natural Gas": "NG=F"
    }

    for name, ticker in commodities.items():
        try:
            comm = yf.Ticker(ticker)
            comm_hist = comm.history(period="5d")
            if not comm_hist.empty and len(comm_hist) >= 2:
                current = comm_hist['Close'].iloc[-1]
                prev = comm_hist['Close'].iloc[-2]
                change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0
                result["commodities"][name] = {
                    "price": round(current, 2),
                    "change_percent": round(change_pct, 2)
                }
        except Exception:
            pass

    # 시장 심리 판단 (VIX 기반)
    vix_data = result["volatility"].get("VIX", {})
    if vix_data:
        vix_value = vix_data.get("value", 20)
        sp500_change = result["indices"].get("S&P 500", {}).get("change_percent", 0)

        if vix_value > 25 and sp500_change < -1:
            result["market_sentiment"] = "극도의 공포 (매수 기회 가능)"
        elif vix_value > 20:
            result["market_sentiment"] = "불안 (신중한 접근 필요)"
        elif vix_value < 15 and sp500_change > 0:
            result["market_sentiment"] = "낙관 (과열 주의)"
        else:
            result["market_sentiment"] = "중립"

    return result


# =============================================================================
# 메인 함수 - CLI 모드 실행용
# (Streamlit 앱에서는 이 함수를 사용하지 않음)
# =============================================================================
def main():
    """메인 함수 - Agent 초기화 및 대화 루프

    CLI(Command Line Interface) 모드로 직접 실행할 때 사용됩니다.
    터미널에서 회사명을 입력하면 AI가 분석 결과를 출력합니다.
    """

    # 로컬 계정 기반 AI 모델 초기화 (agy CLI, AI_PROVIDER=gemini|claude)
    ai_model = create_agent_model()

    # AI 에이전트 생성
    # - model: 사용할 LLM 모델
    # - tools: AgyCliModel은 도구 호출(tool use)을 지원하지 않으므로 비워둠
    #   (CLI 모드 사용 시 회사명만 넘겨 텍스트 응답을 받는다)
    # - system_prompt: AI의 역할과 동작 방식 정의
    agent = Agent(
        model=ai_model,
        tools=[],
        system_prompt="""당신은 주식 정보 도우미입니다.

**사용자 입력 처리:**
- 사용자가 "삼성전자", "삼성전자 주가", "삼성전자 분석" 등을 입력하면 회사명은 "삼성전자"입니다
- "주가", "분석", "매수", "매도" 같은 키워드는 무시하고 회사명만 추출하세요
- 예: "삼성전자 주가분석" → company_name="삼성전자"
- 예: "SK 하이닉스 매수 타이밍" → company_name="SK 하이닉스"

**중요: 도구 호출 시 회사명을 절대 번역하지 마세요**
- 사용자: "삼성전자" → company_name="삼성전자" (O)
- 사용자: "삼성전자" → company_name="Samsung Electronics" (X)
- 사용자: "005930" → company_name="005930" (O)

**종합 분석 요청 시 반드시 3가지 도구 모두 사용:**
1. get_stock_price - 현재가 확인
2. analyze_stock_trend - 기술적 분석
3. analyze_company_news - 뉴스 감성 분석

**주가 분석 시 매수/매도 신호를 명확히 표시:**

✅ 매수 신호 (긍정적):
- 현재가 > 이동평균선 (상승 추세)
- RSI < 30 (과매도, 반등 가능성)
- RSI 30-50 (안정적 매수 구간)
- 거래량 증가 + 가격 상승
- 골든크로스 발생 (단기 이평선이 장기 이평선 상향 돌파)
- MACD > Signal (상승 모멘텀)
- 볼린저밴드 하단 근처 (20% 이하)

❌ 매도 신호 (부정적):
- 현재가 < 이동평균선 (하락 추세)
- RSI > 70 (과매수, 조정 가능성)
- 거래량 감소 + 가격 하락
- 데드크로스 발생 (단기 이평선이 장기 이평선 하향 돌파)
- MACD < Signal (하락 모멘텀)
- 볼린저밴드 상단 근처 (80% 이상)

⚠️ 중립 (관망):
- RSI 50-70 (상승 중이나 과열 주의)
- 볼린저밴드 중간 (40-60%)
- 혼조된 신호들

**분석 결과 형식:**
```
📊 종합 판단: [매수 고려 / 매도 고려 / 관망 추천]

긍정 요인:
- [구체적 이유]

부정 요인:
- [구체적 이유]

📰 뉴스 분석:
- [최근 뉴스 제목과 긍정/부정 판단]
- 뉴스 제목을 보고 회사에 긍정적인지 부정적인지 판단하세요
- 긍정 키워드: 실적 개선, 신제품, 투자 확대, 수주, 협력
- 부정 키워드: 실적 악화, 리콜, 소송, 감원, 적자

⚠️ 투자 판단은 본인의 책임이며, 이 분석은 참고용입니다.
```

예시:
- 사용자: "삼성전자" → company_name="삼성전자" (O)
- 사용자: "051910" → company_name="051910" (O)
- 사용자: "Amazon" → company_name="Amazon" (O)

반드시 한글로 답변하며, 다음 형식을 따르세요:
- 미국 주식: "현재 {회사명}의 주가는 ${가격}입니다. 어제 대비 {변동률}% {상승/하락}하였습니다."
- 한국 주식: "현재 {회사명}의 주가는 {가격}원입니다. 어제 대비 {변동률}% {상승/하락}하였습니다."
"""
    )
    
    # 사용자 인터페이스 시작
    print("=== 주식 정보 AI Agent ===")
    print("회사명을 입력하세요 (예: Amazon, 아마존, 삼성전자, 네이버)")
    print("종료하려면 'quit' 입력\n")
    
    # 대화 루프
    while True:
        try:
            # 사용자 입력 받기 (인코딩 에러 처리)
            user_input = input("회사명: ").strip()
        except (UnicodeDecodeError, EOFError):
            print("\n입력 오류가 발생했습니다. 다시 시도해주세요.")
            continue
        
        # 종료 명령 확인
        if user_input.lower() in ['quit', 'exit', '종료']:
            print("종료합니다.")
            break
        
        # 빈 입력 무시
        if not user_input:
            continue
        
        try:
            # Agent 실행 (도구 호출 및 응답 생성)
            response = agent(user_input)
            print(f"\n{response}\n")
        except Exception as e:
            # 에러 발생 시 사용자에게 안내
            print(f"\n오류가 발생했습니다: {str(e)}\n다시 시도해주세요.\n")


# =============================================================================
# CLI 모드 진입점
# 터미널에서 직접 실행: python stock_agent.py
# =============================================================================
# =============================================================================
# 도구 8: 시장 현황 대시보드 (Market Overview)
# =============================================================================
@tool
def get_market_movers() -> dict:
    """시장 현황을 조회합니다. 급등/급락 종목, 거래량 TOP 종목을 제공합니다.

    포함 정보:
    - 거래량 TOP 종목 (한국/미국)
    - 급등 종목 (일간 상승률 상위)
    - 급락 종목 (일간 하락률 상위)
    - 52주 신고가/신저가 종목

    Returns:
        시장 현황 데이터 (거래량 TOP, 급등/급락 종목)
    """
    import warnings
    warnings.filterwarnings('ignore')

    result = {
        "volume_leaders": [],      # 거래량 TOP
        "gainers": [],             # 급등 종목
        "losers": [],              # 급락 종목
        "near_52w_high": [],       # 52주 신고가 근접
        "near_52w_low": [],        # 52주 신저가 근접
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    # 주요 종목 리스트 (한국 + 미국)
    tickers = [
        # 한국 대표 종목
        ("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"),
        ("035420.KS", "네이버"), ("035720.KS", "카카오"),
        ("005380.KS", "현대차"), ("066570.KS", "LG전자"),
        ("051910.KS", "LG화학"), ("006400.KS", "삼성SDI"),
        ("003670.KS", "포스코퓨처엠"), ("373220.KS", "LG에너지솔루션"),
        # 미국 대표 종목
        ("AAPL", "Apple"), ("MSFT", "Microsoft"),
        ("GOOGL", "Google"), ("AMZN", "Amazon"),
        ("NVDA", "Nvidia"), ("TSLA", "Tesla"),
        ("META", "Meta"), ("AMD", "AMD"),
    ]

    stock_data = []

    for ticker, name in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            info = stock.info

            if hist.empty or len(hist) < 2:
                continue

            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            volume = hist['Volume'].iloc[-1]
            change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0

            # 52주 고가/저가
            high_52w = info.get('fiftyTwoWeekHigh', current)
            low_52w = info.get('fiftyTwoWeekLow', current)

            # 52주 범위 내 위치 (%)
            range_52w = high_52w - low_52w
            position_52w = ((current - low_52w) / range_52w * 100) if range_52w > 0 else 50

            stock_data.append({
                "ticker": ticker,
                "name": name,
                "price": round(current, 2),
                "change_percent": round(change_pct, 2),
                "volume": int(volume),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "position_52w": round(position_52w, 1)
            })
        except Exception:
            continue

    # 거래량 TOP 5
    volume_sorted = sorted(stock_data, key=lambda x: x['volume'], reverse=True)
    result["volume_leaders"] = volume_sorted[:5]

    # 급등 TOP 5 (상승률 높은 순)
    gainers_sorted = sorted([s for s in stock_data if s['change_percent'] > 0],
                           key=lambda x: x['change_percent'], reverse=True)
    result["gainers"] = gainers_sorted[:5]

    # 급락 TOP 5 (하락률 높은 순)
    losers_sorted = sorted([s for s in stock_data if s['change_percent'] < 0],
                          key=lambda x: x['change_percent'])
    result["losers"] = losers_sorted[:5]

    # 52주 신고가 근접 (90% 이상)
    near_high = [s for s in stock_data if s['position_52w'] >= 90]
    result["near_52w_high"] = sorted(near_high, key=lambda x: x['position_52w'], reverse=True)[:5]

    # 52주 신저가 근접 (10% 이하)
    near_low = [s for s in stock_data if s['position_52w'] <= 10]
    result["near_52w_low"] = sorted(near_low, key=lambda x: x['position_52w'])[:5]

    return result


# =============================================================================
# 도구 9: 테마별 종목 (Theme Stocks)
# =============================================================================
THEME_STOCKS = {
    "AI/반도체": {
        "description": "인공지능 및 반도체 관련 종목",
        "stocks": [
            ("NVDA", "Nvidia", "AI GPU 선두"),
            ("AMD", "AMD", "CPU/GPU"),
            ("AVGO", "Broadcom", "AI 네트워킹"),
            ("000660.KS", "SK하이닉스", "HBM 메모리"),
            ("005930.KS", "삼성전자", "메모리 반도체"),
        ]
    },
    "전기차/배터리": {
        "description": "전기차 및 2차전지 관련 종목",
        "stocks": [
            ("TSLA", "Tesla", "전기차 선두"),
            ("373220.KS", "LG에너지솔루션", "배터리"),
            ("006400.KS", "삼성SDI", "배터리"),
            ("051910.KS", "LG화학", "배터리 소재"),
            ("003670.KS", "포스코퓨처엠", "양극재"),
        ]
    },
    "빅테크": {
        "description": "미국 대형 기술주",
        "stocks": [
            ("AAPL", "Apple", "아이폰/서비스"),
            ("MSFT", "Microsoft", "클라우드/AI"),
            ("GOOGL", "Google", "검색/클라우드"),
            ("AMZN", "Amazon", "이커머스/AWS"),
            ("META", "Meta", "SNS/메타버스"),
        ]
    },
    "K-플랫폼": {
        "description": "한국 플랫폼/인터넷 기업",
        "stocks": [
            ("035420.KS", "네이버", "검색/커머스"),
            ("035720.KS", "카카오", "메신저/핀테크"),
            ("263750.KS", "펄어비스", "게임"),
            ("251270.KS", "넷마블", "게임"),
            ("036570.KS", "엔씨소프트", "게임"),
        ]
    },
    "배당주": {
        "description": "고배당 우량주",
        "stocks": [
            ("KO", "Coca-Cola", "배당귀족"),
            ("JNJ", "Johnson & Johnson", "헬스케어"),
            ("PG", "Procter & Gamble", "소비재"),
            ("017670.KS", "SK텔레콤", "통신"),
            ("030200.KS", "KT", "통신"),
        ]
    }
}


@tool
def get_theme_stocks(theme_name: str = None) -> dict:
    """테마별 종목을 조회합니다.

    사용 가능한 테마:
    - AI/반도체: 인공지능, GPU, 메모리 반도체
    - 전기차/배터리: 전기차, 2차전지, 배터리 소재
    - 빅테크: 미국 대형 기술주 (FAANG+)
    - K-플랫폼: 한국 인터넷/플랫폼 기업
    - 배당주: 고배당 우량주

    Args:
        theme_name: 테마명 (None이면 전체 테마 목록 반환)

    Returns:
        테마별 종목 및 현재가 정보
    """
    if theme_name is None:
        # 전체 테마 목록 반환
        return {
            "themes": list(THEME_STOCKS.keys()),
            "descriptions": {k: v["description"] for k, v in THEME_STOCKS.items()}
        }

    # 테마 찾기 (부분 일치)
    matched_theme = None
    for theme_key in THEME_STOCKS:
        if theme_name in theme_key or theme_key in theme_name:
            matched_theme = theme_key
            break

    if not matched_theme:
        return {"error": f"'{theme_name}' 테마를 찾을 수 없습니다. 사용 가능: {list(THEME_STOCKS.keys())}"}

    theme_data = THEME_STOCKS[matched_theme]
    stocks_with_price = []

    for ticker, name, description in theme_data["stocks"]:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")

            if hist.empty:
                continue

            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
            change_pct = ((current - prev) / prev) * 100 if prev > 0 else 0

            stocks_with_price.append({
                "ticker": ticker,
                "name": name,
                "description": description,
                "price": round(current, 2),
                "change_percent": round(change_pct, 2)
            })
        except Exception:
            stocks_with_price.append({
                "ticker": ticker,
                "name": name,
                "description": description,
                "price": None,
                "change_percent": None
            })

    return {
        "theme": matched_theme,
        "description": theme_data["description"],
        "stocks": stocks_with_price,
        "stock_count": len(stocks_with_price)
    }


# =============================================================================
# 도구 10: 배당금 정보 (Dividend Info)
# =============================================================================
@tool
def get_dividend_info(company_name: str) -> dict:
    """종목의 배당금 정보를 조회합니다.

    포함 정보:
    - 배당 수익률
    - 주당 배당금
    - 배당 지급 주기
    - 최근 배당 내역
    - 배당 성장률

    Args:
        company_name: 회사명

    Returns:
        배당금 관련 정보
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        dividends = stock.dividends
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    # 배당 수익률
    dividend_yield = info.get('dividendYield')
    dividend_rate = info.get('dividendRate')
    payout_ratio = info.get('payoutRatio')
    ex_dividend_date = info.get('exDividendDate')

    # 최근 배당 내역
    recent_dividends = []
    if dividends is not None and not dividends.empty:
        for date, amount in dividends.tail(4).items():
            recent_dividends.append({
                "date": date.strftime("%Y-%m-%d"),
                "amount": round(amount, 4)
            })

    # 배당 성장률 계산
    dividend_growth = None
    if len(recent_dividends) >= 2:
        recent = recent_dividends[-1]['amount']
        oldest = recent_dividends[0]['amount']
        if oldest > 0:
            years = len(recent_dividends) - 1
            dividend_growth = ((recent / oldest) ** (1/years) - 1) * 100 if years > 0 else 0

    # 배당락일 처리
    ex_date_str = None
    if ex_dividend_date:
        try:
            ex_date_str = datetime.fromtimestamp(ex_dividend_date).strftime("%Y-%m-%d")
        except Exception:
            pass

    return {
        "company": company_name,
        "ticker": ticker,
        "dividend_yield": round(dividend_yield * 100, 2) if dividend_yield else None,
        "dividend_rate": round(dividend_rate, 4) if dividend_rate else None,
        "payout_ratio": round(payout_ratio * 100, 1) if payout_ratio else None,
        "ex_dividend_date": ex_date_str,
        "recent_dividends": recent_dividends,
        "dividend_growth": round(dividend_growth, 2) if dividend_growth else None,
        "is_dividend_stock": dividend_yield is not None and dividend_yield > 0
    }


# =============================================================================
# 도구 11: Prophet 시계열 예측 (Time Series Forecast)
# =============================================================================
@tool
def get_prophet_forecast(company_name: str, forecast_days: int = 1) -> dict:
    """Prophet 모델을 사용하여 주가를 예측합니다.

    과거 주가 데이터를 기반으로 통계적 시계열 예측을 수행합니다.
    1일 단기 예측에 최적화되어 있습니다.

    Args:
        company_name: 회사명
        forecast_days: 예측 기간 (일 단위, 기본값 1일)

    Returns:
        예측 주가, 신뢰 구간, 추세 정보
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        # 6개월 데이터로 학습 (단기 예측에 최적)
        hist = stock.history(period="6mo")
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    if hist.empty or len(hist) < 30:
        return {"error": "충분한 과거 데이터가 없습니다 (최소 30일 필요)"}

    try:
        # Prophet 형식으로 데이터 준비
        df = pd.DataFrame({
            'ds': hist.index.tz_localize(None),
            'y': hist['Close'].values
        })

        # Prophet 모델 설정 (단기 예측 최적화)
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,  # 6개월 데이터이므로 비활성화
            changepoint_prior_scale=0.1,  # 변화점 감도
            seasonality_prior_scale=0.1,
            interval_width=0.8  # 80% 신뢰 구간
        )

        # 로그 출력 억제
        import logging
        logging.getLogger('prophet').setLevel(logging.WARNING)
        logging.getLogger('cmdstanpy').setLevel(logging.WARNING)

        model.fit(df)

        # 예측 수행
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)

        # 마지막 예측값 추출
        last_forecast = forecast.tail(forecast_days).iloc[-1]
        current_price = hist['Close'].iloc[-1]
        predicted_price = last_forecast['yhat']
        lower_bound = last_forecast['yhat_lower']
        upper_bound = last_forecast['yhat_upper']

        # 추세 분석
        price_change = predicted_price - current_price
        change_percent = (price_change / current_price) * 100

        # 추세 방향 결정
        if change_percent > 1:
            trend = "상승"
        elif change_percent < -1:
            trend = "하락"
        else:
            trend = "보합"

        # 예측 신뢰도 계산 (신뢰 구간 폭 기반)
        confidence_range = upper_bound - lower_bound
        confidence_ratio = confidence_range / current_price * 100
        if confidence_ratio < 3:
            confidence = "높음"
        elif confidence_ratio < 6:
            confidence = "중간"
        else:
            confidence = "낮음"

        return {
            "company": company_name,
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "predicted_price": round(predicted_price, 2),
            "lower_bound": round(lower_bound, 2),
            "upper_bound": round(upper_bound, 2),
            "price_change": round(price_change, 2),
            "change_percent": round(change_percent, 2),
            "trend": trend,
            "confidence": confidence,
            "forecast_days": forecast_days,
            "model": "Prophet"
        }

    except Exception as e:
        return {"error": f"Prophet 예측 실패: {str(e)}"}


# =============================================================================
# 도구 12: 단기 기술적 지표 (Short-term Technical Indicators)
# =============================================================================
@tool
def get_short_term_indicators(company_name: str) -> dict:
    """1일 단기 예측에 유용한 기술적 지표를 계산합니다.

    포함 지표:
    - VWAP (거래량가중평균가)
    - 당일 모멘텀
    - 거래량 급증 감지
    - 5일/10일 단기 이동평균
    - 스토캐스틱 RSI
    - ATR (평균진폭)

    Args:
        company_name: 회사명

    Returns:
        단기 기술적 지표 딕셔너리
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        # 최근 1개월 데이터 (1시간봉이면 더 좋지만 yfinance 제한)
        hist = stock.history(period="1mo")
        # 당일 데이터 (가능한 경우)
        hist_1d = stock.history(period="1d", interval="1h")
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    if hist.empty or len(hist) < 10:
        return {"error": "충분한 데이터가 없습니다"}

    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    volume = hist['Volume']

    current_price = close.iloc[-1]

    # 1. VWAP 계산 (최근 5일)
    typical_price = (high + low + close) / 3
    vwap_5d = (typical_price[-5:] * volume[-5:]).sum() / volume[-5:].sum() if volume[-5:].sum() > 0 else current_price
    vwap_position = ((current_price - vwap_5d) / vwap_5d) * 100

    # 2. 당일 모멘텀 (시가 대비 현재가)
    today_open = hist['Open'].iloc[-1]
    intraday_momentum = ((current_price - today_open) / today_open) * 100

    # 3. 거래량 급증 감지
    avg_volume_20 = volume[-20:].mean() if len(volume) >= 20 else volume.mean()
    current_volume = volume.iloc[-1]
    volume_surge_ratio = (current_volume / avg_volume_20) * 100 if avg_volume_20 > 0 else 100
    volume_surge = volume_surge_ratio > 150  # 평균 대비 150% 이상이면 급증

    # 4. 단기 이동평균
    ma5 = close[-5:].mean() if len(close) >= 5 else current_price
    ma10 = close[-10:].mean() if len(close) >= 10 else current_price

    # MA 크로스 신호
    if ma5 > ma10:
        ma_signal = "골든크로스 (상승)"
    elif ma5 < ma10:
        ma_signal = "데드크로스 (하락)"
    else:
        ma_signal = "중립"

    # 5. 스토캐스틱 RSI (14일)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_current = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    # 스토캐스틱 RSI
    rsi_min = rsi[-14:].min() if len(rsi) >= 14 else 0
    rsi_max = rsi[-14:].max() if len(rsi) >= 14 else 100
    stoch_rsi = ((rsi_current - rsi_min) / (rsi_max - rsi_min) * 100) if (rsi_max - rsi_min) > 0 else 50

    # 6. ATR (평균진폭) - 변동성 지표
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr[-14:].mean() if len(tr) >= 14 else tr.mean()
    atr_percent = (atr / current_price) * 100

    # 7. 종합 단기 신호 계산
    bullish_signals = 0
    bearish_signals = 0

    if vwap_position > 0:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if intraday_momentum > 0:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if ma5 > ma10:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if rsi_current < 30:
        bullish_signals += 1  # 과매도 → 반등 가능
    elif rsi_current > 70:
        bearish_signals += 1  # 과매수 → 조정 가능

    if volume_surge and intraday_momentum > 0:
        bullish_signals += 1  # 거래량 급증 + 상승
    elif volume_surge and intraday_momentum < 0:
        bearish_signals += 1  # 거래량 급증 + 하락

    # 종합 신호
    total_signals = bullish_signals + bearish_signals
    if total_signals > 0:
        bullish_ratio = bullish_signals / total_signals * 100
    else:
        bullish_ratio = 50

    if bullish_ratio >= 70:
        short_term_signal = "강한 매수"
    elif bullish_ratio >= 55:
        short_term_signal = "약한 매수"
    elif bullish_ratio >= 45:
        short_term_signal = "중립"
    elif bullish_ratio >= 30:
        short_term_signal = "약한 매도"
    else:
        short_term_signal = "강한 매도"

    return {
        "company": company_name,
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "vwap_5d": round(vwap_5d, 2),
        "vwap_position": round(vwap_position, 2),
        "intraday_momentum": round(intraday_momentum, 2),
        "volume_surge": volume_surge,
        "volume_surge_ratio": round(volume_surge_ratio, 1),
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma_signal": ma_signal,
        "rsi": round(rsi_current, 1),
        "stochastic_rsi": round(stoch_rsi, 1),
        "atr": round(atr, 2),
        "atr_percent": round(atr_percent, 2),
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals,
        "bullish_ratio": round(bullish_ratio, 1),
        "short_term_signal": short_term_signal
    }


# =============================================================================
# 도구 13: 백테스팅 (Backtesting)
# =============================================================================
@tool
def get_backtest_accuracy(company_name: str, lookback_days: int = 30) -> dict:
    """과거 데이터를 기반으로 Prophet 예측 정확도를 백테스트합니다.

    최근 N일간의 예측 정확도를 계산하여 신뢰도를 평가합니다.

    Args:
        company_name: 회사명
        lookback_days: 백테스트 기간 (기본값 30일)

    Returns:
        예측 정확도 통계
    """
    ticker = get_ticker(company_name)

    try:
        stock = yf.Ticker(ticker)
        # 백테스트를 위해 더 긴 기간 데이터 필요
        hist = stock.history(period="1y")
    except Exception as e:
        return {"error": f"데이터 조회 실패: {str(e)}"}

    if hist.empty or len(hist) < 180:  # 최소 6개월 + 백테스트 기간
        return {"error": "충분한 과거 데이터가 없습니다 (최소 6개월 필요)"}

    try:
        import logging
        logging.getLogger('prophet').setLevel(logging.WARNING)
        logging.getLogger('cmdstanpy').setLevel(logging.WARNING)

        # 백테스트 결과 저장
        predictions = []
        actuals = []
        directions_correct = 0

        # 최근 lookback_days일에 대해 백테스트
        test_days = min(lookback_days, len(hist) - 150)  # 학습 데이터 확보

        for i in range(test_days, 0, -5):  # 5일 간격으로 테스트 (속도 최적화)
            # 학습 데이터 (예측 시점까지)
            train_end = len(hist) - i
            train_data = hist.iloc[:train_end]

            if len(train_data) < 120:  # 최소 학습 데이터
                continue

            # Prophet 모델 학습
            df = pd.DataFrame({
                'ds': train_data.index.tz_localize(None),
                'y': train_data['Close'].values
            })

            model = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.1,
                seasonality_prior_scale=0.1
            )
            model.fit(df)

            # 1일 후 예측
            future = model.make_future_dataframe(periods=1)
            forecast = model.predict(future)
            predicted = forecast['yhat'].iloc[-1]

            # 실제 값
            actual = hist['Close'].iloc[train_end] if train_end < len(hist) else None

            if actual is not None:
                predictions.append(predicted)
                actuals.append(actual)

                # 방향 정확도 (상승/하락 예측)
                prev_price = train_data['Close'].iloc[-1]
                pred_direction = predicted > prev_price
                actual_direction = actual > prev_price
                if pred_direction == actual_direction:
                    directions_correct += 1

        if len(predictions) == 0:
            return {"error": "백테스트 데이터 부족"}

        # 정확도 메트릭 계산
        predictions = np.array(predictions)
        actuals = np.array(actuals)

        # MAE (평균절대오차)
        mae = np.mean(np.abs(predictions - actuals))
        mae_percent = (mae / np.mean(actuals)) * 100

        # MAPE (평균절대백분율오차)
        mape = np.mean(np.abs((actuals - predictions) / actuals)) * 100

        # 방향 정확도
        direction_accuracy = (directions_correct / len(predictions)) * 100

        # 예측 신뢰도 등급
        if mape < 2 and direction_accuracy >= 70:
            reliability = "매우 높음"
        elif mape < 4 and direction_accuracy >= 60:
            reliability = "높음"
        elif mape < 6 and direction_accuracy >= 50:
            reliability = "보통"
        else:
            reliability = "낮음"

        return {
            "company": company_name,
            "ticker": ticker,
            "test_period_days": lookback_days,
            "test_samples": len(predictions),
            "mae": round(mae, 2),
            "mae_percent": round(mae_percent, 2),
            "mape": round(mape, 2),
            "direction_accuracy": round(direction_accuracy, 1),
            "reliability": reliability,
            "description": f"최근 {lookback_days}일간 {len(predictions)}회 예측 테스트 결과"
        }

    except Exception as e:
        return {"error": f"백테스트 실패: {str(e)}"}


if __name__ == "__main__":
    main()
