#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
배치 예측 스크립트 (Daily Batch Prediction)

매일 자동으로 지정된 종목들의 1일, 7일 예측을 생성하고 저장합니다.
cron으로 스케줄링하여 사용합니다.

사용법:
    python batch_prediction.py

크론 설정 예시 (매일 오전 9시 실행):
    0 9 * * * /home/ec2-user/20260208-stock-app-kiro-cli/venv/bin/python /home/ec2-user/20260208-stock-app-kiro-cli/batch_prediction.py >> /home/ec2-user/20260208-stock-app-kiro-cli/logs/batch.log 2>&1
"""

import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Tuple

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_agent import (
    get_stock_price,
    analyze_stock_trend,
    get_prophet_forecast,
    get_short_term_indicators,
    get_fundamental_analysis,
    analyze_company_news,
    get_ticker,
    TICKER_MAP
)

from prediction_tracker import (
    save_prediction,
    update_pending_predictions,
    get_connection
)

# =============================================================================
# 배치 예측 대상 종목 리스트
# =============================================================================
BATCH_STOCKS = [
    # 한국 주식
    {"name": "삼성전자", "ticker": "005930.KS", "market": "KR"},
    {"name": "SK하이닉스", "ticker": "000660.KS", "market": "KR"},
    {"name": "현대자동차", "ticker": "005380.KS", "market": "KR"},
    # 미국 주식
    {"name": "Amazon", "ticker": "AMZN", "market": "US"},
    {"name": "Apple", "ticker": "AAPL", "market": "US"},
    {"name": "Nvidia", "ticker": "NVDA", "market": "US"},
    {"name": "Google", "ticker": "GOOG", "market": "US"},
]

# 예측 기간
FORECAST_PERIODS = ["1일", "7일"]


def log(message: str):
    """타임스탬프와 함께 로그 출력"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_prediction_direction(current_price: float, predicted_price: float) -> str:
    """예측 방향 결정"""
    if predicted_price > current_price * 1.005:  # 0.5% 이상 상승
        return "상승"
    elif predicted_price < current_price * 0.995:  # 0.5% 이상 하락
        return "하락"
    else:
        return "보합"


def generate_prediction_for_stock(stock: Dict, period: str) -> Dict:
    """
    단일 종목에 대한 예측 생성

    Args:
        stock: 종목 정보 딕셔너리
        period: 예측 기간 ("1일" 또는 "7일")

    Returns:
        예측 결과 딕셔너리
    """
    company_name = stock["name"]
    ticker = stock["ticker"]

    try:
        # 1. 현재가 조회
        price_info = get_stock_price(company_name)
        if "error" in price_info:
            return {"error": f"현재가 조회 실패: {price_info['error']}"}

        current_price = float(price_info.get("current_price", 0))
        if current_price <= 0:
            return {"error": "유효하지 않은 현재가"}

        # 2. Prophet 예측
        period_days = {"1일": 1, "7일": 7}
        prophet_result = get_prophet_forecast(company_name, period_days.get(period, 1))
        prophet_price = prophet_result.get("predicted_price") if "error" not in prophet_result else None
        prophet_lower = prophet_result.get("lower_bound") if "error" not in prophet_result else None
        prophet_upper = prophet_result.get("upper_bound") if "error" not in prophet_result else None
        prophet_confidence = prophet_result.get("confidence", "중간") if "error" not in prophet_result else "낮음"

        # 3. 단기 지표 (1일 예측에만 사용)
        short_term = {}
        short_term_signal = "중립"
        bullish_ratio = 50.0

        if period == "1일":
            short_term = get_short_term_indicators(company_name)
            if "error" not in short_term:
                short_term_signal = short_term.get("short_term_signal", "중립")
                bullish_ratio = short_term.get("bullish_ratio", 50.0)

        # 4. 기술적 분석
        analysis = analyze_stock_trend(company_name, "3mo")
        rsi = analysis.get("rsi", 50) if "error" not in analysis else 50

        # 5. 뉴스 감성
        news = analyze_company_news(company_name)
        news_score = news.get("overall_sentiment", {}).get("score", 0) if "error" not in news else 0

        # 6. 앙상블 예측가 계산
        # Prophet 기반으로 단기 지표와 뉴스 감성을 반영하여 조정
        if prophet_price:
            # 기본: Prophet 예측가
            predicted_price = prophet_price

            # 단기 지표 반영 (1일 예측)
            if period == "1일" and "error" not in short_term:
                # 매수 신호가 강하면 상향, 매도 신호가 강하면 하향
                signal_adjustment = (bullish_ratio - 50) / 100 * 0.02  # 최대 ±1% 조정
                predicted_price *= (1 + signal_adjustment)

            # 뉴스 감성 반영
            news_adjustment = news_score / 100 * 0.01  # 최대 ±1% 조정
            predicted_price *= (1 + news_adjustment)

            # RSI 과매수/과매도 반영
            if rsi > 70:  # 과매수
                predicted_price *= 0.99  # 1% 하향
            elif rsi < 30:  # 과매도
                predicted_price *= 1.01  # 1% 상향
        else:
            # Prophet 실패 시 현재가 기준 추정
            predicted_price = current_price * (1 + news_score / 1000)

        # 예측 방향
        direction = get_prediction_direction(current_price, predicted_price)
        change_percent = ((predicted_price - current_price) / current_price) * 100

        return {
            "success": True,
            "company_name": company_name,
            "ticker": ticker,
            "forecast_period": period,
            "current_price": current_price,
            "predicted_price": round(predicted_price, 2),
            "change_percent": round(change_percent, 2),
            "direction": direction,
            "prophet_price": prophet_price,
            "prophet_lower": prophet_lower,
            "prophet_upper": prophet_upper,
            "prophet_confidence": prophet_confidence,
            "short_term_signal": short_term_signal,
            "bullish_ratio": bullish_ratio,
            "rsi": rsi,
            "news_score": news_score
        }

    except Exception as e:
        return {"error": str(e)}


def save_batch_prediction(prediction: Dict) -> int:
    """
    배치 예측 결과를 데이터베이스에 저장

    Returns:
        저장된 레코드 ID
    """
    return save_prediction(
        company_name=prediction["company_name"],
        ticker=prediction["ticker"],
        forecast_period=prediction["forecast_period"],
        current_price=prediction["current_price"],
        predicted_price=prediction["predicted_price"],
        prophet_price=prediction.get("prophet_price"),
        prophet_lower=prediction.get("prophet_lower"),
        prophet_upper=prediction.get("prophet_upper"),
        short_term_signal=prediction.get("short_term_signal"),
        bullish_ratio=prediction.get("bullish_ratio"),
        notes=f"배치예측 - 방향:{prediction['direction']}, 변동:{prediction['change_percent']}%"
    )


def run_batch_predictions():
    """
    모든 대상 종목에 대해 배치 예측 실행
    """
    log("=" * 60)
    log("배치 예측 시작")
    log(f"대상 종목: {len(BATCH_STOCKS)}개")
    log(f"예측 기간: {FORECAST_PERIODS}")
    log("=" * 60)

    # 먼저 대기 중인 예측 업데이트 (실제 가격 반영)
    log("대기 중인 예측 업데이트 중...")
    try:
        updated = update_pending_predictions()
        log(f"→ {updated}건 업데이트 완료")
    except Exception as e:
        log(f"→ 업데이트 실패: {e}")

    results = {
        "success": 0,
        "failed": 0,
        "predictions": []
    }

    for stock in BATCH_STOCKS:
        for period in FORECAST_PERIODS:
            log(f"\n[{stock['name']}] {period} 예측 생성 중...")

            try:
                # 예측 생성
                prediction = generate_prediction_for_stock(stock, period)

                if "error" in prediction:
                    log(f"→ 실패: {prediction['error']}")
                    results["failed"] += 1
                    continue

                # 데이터베이스 저장
                record_id = save_batch_prediction(prediction)
                prediction["record_id"] = record_id

                log(f"→ 성공: 현재가 {prediction['current_price']:,.0f} → "
                    f"예측가 {prediction['predicted_price']:,.0f} "
                    f"({prediction['direction']}, {prediction['change_percent']:+.2f}%)")

                results["success"] += 1
                results["predictions"].append(prediction)

                # API 호출 간 딜레이 (rate limit 방지)
                time.sleep(2)

            except Exception as e:
                log(f"→ 예외 발생: {e}")
                results["failed"] += 1

    log("\n" + "=" * 60)
    log("배치 예측 완료")
    log(f"성공: {results['success']}건, 실패: {results['failed']}건")
    log("=" * 60)

    return results


def get_batch_stocks_list() -> List[Dict]:
    """배치 예측 대상 종목 리스트 반환 (외부 모듈에서 사용)"""
    return BATCH_STOCKS


if __name__ == "__main__":
    # 로그 디렉토리 생성
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    # 배치 예측 실행
    results = run_batch_predictions()

    # 결과 요약 출력
    print("\n=== 예측 결과 요약 ===")
    for pred in results.get("predictions", []):
        market_symbol = "₩" if pred["ticker"].endswith(".KS") else "$"
        print(f"{pred['company_name']} ({pred['forecast_period']}): "
              f"{market_symbol}{pred['current_price']:,.0f} → "
              f"{market_symbol}{pred['predicted_price']:,.0f} "
              f"[{pred['direction']}]")
