#!/bin/bash
# =============================================================================
# 배치 예측 크론잡 설정 스크립트
#
# 매일 오전 9시(KST)에 7개 종목의 1일/7일 예측을 자동으로 생성합니다.
# =============================================================================

# 경로 설정
PROJECT_DIR="/home/ec2-user/20260208-stock-app-kiro-cli"
VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"
BATCH_SCRIPT="${PROJECT_DIR}/batch_prediction.py"
LOG_DIR="${PROJECT_DIR}/logs"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 크론잡 내용 (매일 오전 9시 KST = UTC 0시)
# 한국 시장: 오전 9시 개장 전
# 미국 시장: 전일 장 마감 후
CRON_JOB="0 0 * * * cd ${PROJECT_DIR} && ${VENV_PYTHON} ${BATCH_SCRIPT} >> ${LOG_DIR}/batch_\$(date +\%Y\%m\%d).log 2>&1"

# 현재 사용자의 크론탭 가져오기
CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")

# 이미 등록된 배치 예측 작업이 있는지 확인
if echo "$CURRENT_CRON" | grep -q "batch_prediction.py"; then
    echo "⚠️  배치 예측 크론잡이 이미 등록되어 있습니다."
    echo "현재 크론탭:"
    crontab -l | grep "batch_prediction"
    echo ""
    read -p "기존 작업을 교체하시겠습니까? (y/n): " REPLACE
    if [ "$REPLACE" = "y" ]; then
        # 기존 배치 예측 작업 제거
        CURRENT_CRON=$(echo "$CURRENT_CRON" | grep -v "batch_prediction.py")
    else
        echo "취소되었습니다."
        exit 0
    fi
fi

# 새 크론잡 추가
echo "${CURRENT_CRON}
${CRON_JOB}" | crontab -

echo "✅ 크론잡이 성공적으로 등록되었습니다!"
echo ""
echo "등록된 작업:"
crontab -l | grep "batch_prediction"
echo ""
echo "📅 실행 시간: 매일 오전 9시 (KST)"
echo "📁 로그 위치: ${LOG_DIR}/batch_YYYYMMDD.log"
echo ""
echo "수동 실행 명령어:"
echo "  cd ${PROJECT_DIR} && ${VENV_PYTHON} ${BATCH_SCRIPT}"
