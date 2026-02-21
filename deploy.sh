#!/bin/bash
# =============================================================================
# Stock AI Agent - ECS Fargate 배포 스크립트
# Docker 이미지 빌드 및 ECR 푸시, ECS 서비스 업데이트
# =============================================================================
set -e

# 설정 변수
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="stock-app"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ECS_CLUSTER_NAME="StockAppCluster"
ECS_SERVICE_NAME="StockAppService"

# 색상 출력
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Stock AI Agent - ECS 배포 시작${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "AWS Account: ${YELLOW}${AWS_ACCOUNT_ID}${NC}"
echo -e "Region: ${YELLOW}${AWS_REGION}${NC}"
echo -e "ECR Repository: ${YELLOW}${ECR_REPO_NAME}${NC}"
echo -e "Image Tag: ${YELLOW}${IMAGE_TAG}${NC}"
echo ""

# ECR 레포지토리 URI
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

# 1. ECR 레포지토리 생성 (존재하지 않는 경우)
echo -e "${YELLOW}[1/5] ECR 레포지토리 확인/생성 중...${NC}"
if ! aws ecr describe-repositories --repository-names ${ECR_REPO_NAME} --region ${AWS_REGION} > /dev/null 2>&1; then
    echo "ECR 레포지토리 생성: ${ECR_REPO_NAME}"
    aws ecr create-repository \
        --repository-name ${ECR_REPO_NAME} \
        --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256
    echo -e "${GREEN}ECR 레포지토리 생성 완료${NC}"
else
    echo -e "${GREEN}ECR 레포지토리 이미 존재${NC}"
fi

# 2. ECR 로그인
echo -e "${YELLOW}[2/5] ECR 로그인 중...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
echo -e "${GREEN}ECR 로그인 완료${NC}"

# 3. Docker 이미지 빌드
echo -e "${YELLOW}[3/5] Docker 이미지 빌드 중...${NC}"
docker build -t ${ECR_REPO_NAME}:${IMAGE_TAG} .
echo -e "${GREEN}Docker 이미지 빌드 완료${NC}"

# 4. ECR에 이미지 푸시
echo -e "${YELLOW}[4/5] ECR에 이미지 푸시 중...${NC}"
docker tag ${ECR_REPO_NAME}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}
docker push ${ECR_URI}:${IMAGE_TAG}
echo -e "${GREEN}ECR 이미지 푸시 완료${NC}"

# 5. ECS 서비스 업데이트 (선택적)
echo -e "${YELLOW}[5/5] ECS 서비스 업데이트 확인 중...${NC}"
if aws ecs describe-services --cluster ${ECS_CLUSTER_NAME} --services ${ECS_SERVICE_NAME} --region ${AWS_REGION} > /dev/null 2>&1; then
    echo "ECS 서비스 업데이트 중..."
    aws ecs update-service \
        --cluster ${ECS_CLUSTER_NAME} \
        --service ${ECS_SERVICE_NAME} \
        --force-new-deployment \
        --region ${AWS_REGION}
    echo -e "${GREEN}ECS 서비스 업데이트 완료${NC}"
else
    echo -e "${YELLOW}ECS 서비스가 아직 존재하지 않습니다. CDK 배포 후 다시 실행하세요.${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}배포 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "ECR 이미지: ${YELLOW}${ECR_URI}:${IMAGE_TAG}${NC}"
echo ""
echo -e "다음 단계:"
echo -e "  1. CDK 배포: ${YELLOW}cd cdk && cdk deploy${NC}"
echo -e "  2. CloudFront URL 확인: CDK 출력 참조"
