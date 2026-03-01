#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예측 기록 추적 모듈 (Prediction Tracker)

예측 결과를 SQLite에 저장하고, 나중에 실제 가격과 비교하여
예측 정확도를 추적합니다.

저장 데이터:
- 예측 생성 시간
- 예측 대상 날짜
- 종목 정보
- 예측가 (AI + Prophet)
- 실제가 (나중에 업데이트)
- 정확도 메트릭
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import yfinance as yf

# 데이터베이스 파일 경로
DB_PATH = os.path.join(os.path.dirname(__file__), 'predictions.db')


def get_connection():
    """SQLite 연결 반환"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 딕셔너리처럼 접근 가능
    return conn


def init_database():
    """데이터베이스 초기화 (테이블 생성)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            target_date DATE NOT NULL,
            company_name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            forecast_period TEXT NOT NULL,
            current_price REAL NOT NULL,
            predicted_price REAL,
            prophet_price REAL,
            prophet_lower REAL,
            prophet_upper REAL,
            short_term_signal TEXT,
            bullish_ratio REAL,
            actual_price REAL,
            is_correct_direction INTEGER,
            error_percent REAL,
            prophet_error_percent REAL,
            updated_at TIMESTAMP,
            notes TEXT
        )
    ''')

    # 인덱스 생성 (조회 속도 향상)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticker ON predictions(ticker)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_target_date ON predictions(target_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_forecast_period ON predictions(forecast_period)')

    conn.commit()
    conn.close()


def save_prediction(
    company_name: str,
    ticker: str,
    forecast_period: str,
    current_price: float,
    predicted_price: Optional[float],
    prophet_price: Optional[float],
    prophet_lower: Optional[float] = None,
    prophet_upper: Optional[float] = None,
    short_term_signal: Optional[str] = None,
    bullish_ratio: Optional[float] = None,
    notes: Optional[str] = None
) -> int:
    """
    예측 결과 저장

    Returns:
        저장된 레코드 ID
    """
    # 예측 대상 날짜 계산
    period_days = {
        "1일": 1, "7일": 7, "1개월": 30, "3개월": 90, "6개월": 180
    }
    days = period_days.get(forecast_period, 1)
    target_date = datetime.now() + timedelta(days=days)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO predictions (
            target_date, company_name, ticker, forecast_period,
            current_price, predicted_price, prophet_price,
            prophet_lower, prophet_upper, short_term_signal,
            bullish_ratio, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        target_date.strftime('%Y-%m-%d'),
        company_name, ticker, forecast_period,
        current_price, predicted_price, prophet_price,
        prophet_lower, prophet_upper, short_term_signal,
        bullish_ratio, notes
    ))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return record_id


def update_actual_price(prediction_id: int, actual_price: float) -> Dict:
    """
    실제 가격으로 예측 결과 업데이트

    Returns:
        업데이트된 정확도 정보
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 기존 레코드 조회
    cursor.execute('SELECT * FROM predictions WHERE id = ?', (prediction_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"error": "예측 기록을 찾을 수 없습니다."}

    current_price = row['current_price']
    predicted_price = row['predicted_price']
    prophet_price = row['prophet_price']

    # 방향 정확도 계산
    actual_direction = actual_price > current_price  # 상승 여부
    predicted_direction = predicted_price > current_price if predicted_price else None
    is_correct = 1 if predicted_direction == actual_direction else 0

    # 오차율 계산
    error_percent = None
    if predicted_price:
        error_percent = ((actual_price - predicted_price) / predicted_price) * 100

    prophet_error_percent = None
    if prophet_price:
        prophet_error_percent = ((actual_price - prophet_price) / prophet_price) * 100

    # 업데이트
    cursor.execute('''
        UPDATE predictions SET
            actual_price = ?,
            is_correct_direction = ?,
            error_percent = ?,
            prophet_error_percent = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (actual_price, is_correct, error_percent, prophet_error_percent, prediction_id))

    conn.commit()
    conn.close()

    return {
        "prediction_id": prediction_id,
        "actual_price": actual_price,
        "is_correct_direction": bool(is_correct),
        "error_percent": round(error_percent, 2) if error_percent else None,
        "prophet_error_percent": round(prophet_error_percent, 2) if prophet_error_percent else None
    }


def update_pending_predictions():
    """
    대상 날짜가 지난 예측들의 실제 가격 업데이트

    Returns:
        업데이트된 예측 수
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 대상 날짜가 지났고, 실제 가격이 없는 예측 조회
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT id, ticker, target_date FROM predictions
        WHERE target_date <= ? AND actual_price IS NULL
    ''', (today,))

    pending = cursor.fetchall()
    updated_count = 0

    for row in pending:
        try:
            # yfinance로 실제 가격 조회
            stock = yf.Ticker(row['ticker'])
            target_date = datetime.strptime(row['target_date'], '%Y-%m-%d')

            # 대상 날짜의 종가 조회
            hist = stock.history(
                start=target_date - timedelta(days=3),
                end=target_date + timedelta(days=3)
            )

            if not hist.empty:
                # 대상 날짜에 가장 가까운 거래일의 종가
                actual_price = hist['Close'].iloc[-1]
                update_actual_price(row['id'], actual_price)
                updated_count += 1
        except Exception as e:
            print(f"Error updating prediction {row['id']}: {e}")
            continue

    conn.close()
    return updated_count


def get_prediction_stats(ticker: Optional[str] = None, days: int = 30) -> Dict:
    """
    예측 정확도 통계 조회

    Args:
        ticker: 특정 종목만 조회 (None이면 전체)
        days: 최근 N일간의 예측

    Returns:
        정확도 통계 딕셔너리
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 기본 쿼리
    query = '''
        SELECT
            COUNT(*) as total_predictions,
            SUM(CASE WHEN actual_price IS NOT NULL THEN 1 ELSE 0 END) as verified_predictions,
            SUM(CASE WHEN is_correct_direction = 1 THEN 1 ELSE 0 END) as correct_directions,
            AVG(ABS(error_percent)) as avg_error_percent,
            AVG(ABS(prophet_error_percent)) as avg_prophet_error_percent,
            forecast_period
        FROM predictions
        WHERE created_at >= datetime('now', ?)
    '''

    params = [f'-{days} days']

    if ticker:
        query += ' AND ticker = ?'
        params.append(ticker)

    query += ' GROUP BY forecast_period'

    cursor.execute(query, params)
    rows = cursor.fetchall()

    stats = {
        "period_stats": [],
        "summary": {
            "total": 0,
            "verified": 0,
            "correct": 0,
            "direction_accuracy": 0,
            "avg_error": 0
        }
    }

    total_correct = 0
    total_verified = 0
    total_error = 0
    error_count = 0

    for row in rows:
        verified = row['verified_predictions'] or 0
        correct = row['correct_directions'] or 0
        direction_accuracy = (correct / verified * 100) if verified > 0 else 0

        stats["period_stats"].append({
            "period": row['forecast_period'],
            "total": row['total_predictions'],
            "verified": verified,
            "correct": correct,
            "direction_accuracy": round(direction_accuracy, 1),
            "avg_error": round(row['avg_error_percent'], 2) if row['avg_error_percent'] else None,
            "prophet_avg_error": round(row['avg_prophet_error_percent'], 2) if row['avg_prophet_error_percent'] else None
        })

        stats["summary"]["total"] += row['total_predictions']
        total_verified += verified
        total_correct += correct
        if row['avg_error_percent']:
            total_error += row['avg_error_percent']
            error_count += 1

    stats["summary"]["verified"] = total_verified
    stats["summary"]["correct"] = total_correct
    stats["summary"]["direction_accuracy"] = round(
        (total_correct / total_verified * 100) if total_verified > 0 else 0, 1
    )
    stats["summary"]["avg_error"] = round(
        total_error / error_count if error_count > 0 else 0, 2
    )

    conn.close()
    return stats


def get_recent_predictions(limit: int = 20, ticker: Optional[str] = None) -> List[Dict]:
    """
    최근 예측 기록 조회

    Returns:
        예측 기록 리스트
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = '''
        SELECT * FROM predictions
        WHERE 1=1
    '''
    params = []

    if ticker:
        query += ' AND ticker = ?'
        params.append(ticker)

    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    predictions = []
    for row in rows:
        predictions.append({
            "id": row['id'],
            "created_at": row['created_at'],
            "target_date": row['target_date'],
            "company_name": row['company_name'],
            "ticker": row['ticker'],
            "forecast_period": row['forecast_period'],
            "current_price": row['current_price'],
            "predicted_price": row['predicted_price'],
            "prophet_price": row['prophet_price'],
            "actual_price": row['actual_price'],
            "is_correct_direction": bool(row['is_correct_direction']) if row['is_correct_direction'] is not None else None,
            "error_percent": row['error_percent'],
            "status": "검증완료" if row['actual_price'] else "대기중"
        })

    conn.close()
    return predictions


def get_prediction_by_id(prediction_id: int) -> Optional[Dict]:
    """특정 예측 기록 조회"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM predictions WHERE id = ?', (prediction_id,))
    row = cursor.fetchone()

    conn.close()

    if row:
        return dict(row)
    return None


def get_accuracy_by_stock(days: int = 90) -> List[Dict]:
    """
    종목별 예측 정확도 통계 조회 (대시보드용)

    Returns:
        종목별 정확도 리스트
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            company_name,
            ticker,
            COUNT(*) as total_predictions,
            SUM(CASE WHEN actual_price IS NOT NULL THEN 1 ELSE 0 END) as verified,
            SUM(CASE WHEN is_correct_direction = 1 THEN 1 ELSE 0 END) as correct,
            AVG(CASE WHEN actual_price IS NOT NULL THEN ABS(error_percent) END) as avg_error,
            AVG(CASE WHEN actual_price IS NOT NULL THEN ABS(prophet_error_percent) END) as prophet_avg_error
        FROM predictions
        WHERE created_at >= datetime('now', ?)
        GROUP BY ticker
        ORDER BY total_predictions DESC
    ''', (f'-{days} days',))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        verified = row['verified'] or 0
        correct = row['correct'] or 0
        accuracy = (correct / verified * 100) if verified > 0 else 0

        results.append({
            "company_name": row['company_name'],
            "ticker": row['ticker'],
            "total": row['total_predictions'],
            "verified": verified,
            "correct": correct,
            "direction_accuracy": round(accuracy, 1),
            "avg_error": round(row['avg_error'], 2) if row['avg_error'] else None,
            "prophet_avg_error": round(row['prophet_avg_error'], 2) if row['prophet_avg_error'] else None
        })

    return results


def get_accuracy_by_period_and_stock(days: int = 90) -> List[Dict]:
    """
    종목 및 예측기간별 정확도 통계 (대시보드용)

    Returns:
        종목+기간별 정확도 리스트
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            company_name,
            ticker,
            forecast_period,
            COUNT(*) as total_predictions,
            SUM(CASE WHEN actual_price IS NOT NULL THEN 1 ELSE 0 END) as verified,
            SUM(CASE WHEN is_correct_direction = 1 THEN 1 ELSE 0 END) as correct,
            AVG(CASE WHEN actual_price IS NOT NULL THEN ABS(error_percent) END) as avg_error
        FROM predictions
        WHERE created_at >= datetime('now', ?)
        GROUP BY ticker, forecast_period
        ORDER BY company_name, forecast_period
    ''', (f'-{days} days',))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        verified = row['verified'] or 0
        correct = row['correct'] or 0
        accuracy = (correct / verified * 100) if verified > 0 else 0

        results.append({
            "company_name": row['company_name'],
            "ticker": row['ticker'],
            "forecast_period": row['forecast_period'],
            "total": row['total_predictions'],
            "verified": verified,
            "correct": correct,
            "direction_accuracy": round(accuracy, 1),
            "avg_error": round(row['avg_error'], 2) if row['avg_error'] else None
        })

    return results


def get_prediction_history_for_chart(ticker: str, days: int = 30) -> List[Dict]:
    """
    차트용 예측 히스토리 조회 (실제가 vs 예측가)

    Returns:
        시계열 데이터 리스트
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            created_at,
            target_date,
            forecast_period,
            current_price,
            predicted_price,
            prophet_price,
            actual_price,
            is_correct_direction,
            error_percent
        FROM predictions
        WHERE ticker = ? AND created_at >= datetime('now', ?)
        ORDER BY created_at ASC
    ''', (ticker, f'-{days} days'))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_daily_accuracy_trend(days: int = 30) -> List[Dict]:
    """
    일별 정확도 추세 (대시보드 차트용)

    Returns:
        일별 정확도 리스트
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            DATE(created_at) as date,
            COUNT(*) as total,
            SUM(CASE WHEN actual_price IS NOT NULL THEN 1 ELSE 0 END) as verified,
            SUM(CASE WHEN is_correct_direction = 1 THEN 1 ELSE 0 END) as correct
        FROM predictions
        WHERE created_at >= datetime('now', ?)
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    ''', (f'-{days} days',))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        verified = row['verified'] or 0
        correct = row['correct'] or 0
        accuracy = (correct / verified * 100) if verified > 0 else None

        results.append({
            "date": row['date'],
            "total": row['total'],
            "verified": verified,
            "correct": correct,
            "accuracy": round(accuracy, 1) if accuracy else None
        })

    return results


def get_all_predictions_for_dashboard(limit: int = 100) -> List[Dict]:
    """
    대시보드용 전체 예측 기록 조회

    Returns:
        예측 기록 리스트 (최근순)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            id, created_at, target_date, company_name, ticker,
            forecast_period, current_price, predicted_price, prophet_price,
            actual_price, is_correct_direction, error_percent, notes
        FROM predictions
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))

    rows = cursor.fetchall()
    conn.close()

    predictions = []
    for row in rows:
        # 예측 방향 계산
        pred_direction = None
        if row['predicted_price'] and row['current_price']:
            if row['predicted_price'] > row['current_price']:
                pred_direction = "상승"
            elif row['predicted_price'] < row['current_price']:
                pred_direction = "하락"
            else:
                pred_direction = "보합"

        # 실제 방향 계산
        actual_direction = None
        if row['actual_price'] and row['current_price']:
            if row['actual_price'] > row['current_price']:
                actual_direction = "상승"
            elif row['actual_price'] < row['current_price']:
                actual_direction = "하락"
            else:
                actual_direction = "보합"

        predictions.append({
            "id": row['id'],
            "created_at": row['created_at'],
            "target_date": row['target_date'],
            "company_name": row['company_name'],
            "ticker": row['ticker'],
            "forecast_period": row['forecast_period'],
            "current_price": row['current_price'],
            "predicted_price": row['predicted_price'],
            "prophet_price": row['prophet_price'],
            "actual_price": row['actual_price'],
            "pred_direction": pred_direction,
            "actual_direction": actual_direction,
            "is_correct": bool(row['is_correct_direction']) if row['is_correct_direction'] is not None else None,
            "error_percent": row['error_percent'],
            "status": "검증완료" if row['actual_price'] else "대기중"
        })

    return predictions


# 모듈 로드 시 데이터베이스 초기화
init_database()


if __name__ == "__main__":
    # 테스트
    print("=== 예측 추적 시스템 테스트 ===")

    # 테스트 예측 저장
    test_id = save_prediction(
        company_name="삼성전자",
        ticker="005930.KS",
        forecast_period="1일",
        current_price=75000,
        predicted_price=76000,
        prophet_price=75500,
        short_term_signal="약한 매수",
        bullish_ratio=60.0,
        notes="테스트 예측"
    )
    print(f"테스트 예측 저장됨: ID={test_id}")

    # 예측 조회
    predictions = get_recent_predictions(limit=5)
    print(f"\n최근 예측 {len(predictions)}건:")
    for p in predictions:
        print(f"  - {p['company_name']}: {p['current_price']} → {p['predicted_price']} ({p['status']})")

    # 통계 조회
    stats = get_prediction_stats(days=30)
    print(f"\n통계: {stats['summary']}")
