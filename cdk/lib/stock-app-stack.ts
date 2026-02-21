import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export class StockAppStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ==========================================================================
    // VPC 설정
    // ==========================================================================
    const vpc = new ec2.Vpc(this, 'StockAppVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    // ==========================================================================
    // 로깅: ALB 및 CloudFront 액세스 로그용 S3 버킷
    // ==========================================================================
    const logBucket = new s3.Bucket(this, 'AccessLogBucket', {
      bucketName: `stock-app-logs-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
      lifecycleRules: [
        {
          id: 'DeleteOldLogs',
          expiration: cdk.Duration.days(90),
          enabled: true,
        },
      ],
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // ==========================================================================
    // 보안: CloudFront Origin 검증용 비밀 헤더 생성
    // ==========================================================================
    const originVerifySecret = new secretsmanager.Secret(this, 'OriginVerifySecret', {
      description: 'Secret header value for CloudFront to ALB origin verification',
      generateSecretString: {
        excludePunctuation: true,
        passwordLength: 32,
      },
    });

    // ==========================================================================
    // ECR 레포지토리 (기존 레포지토리 참조)
    // ==========================================================================
    const ecrRepository = ecr.Repository.fromRepositoryName(
      this,
      'StockAppRepository',
      'stock-app'
    );

    // ==========================================================================
    // Security Groups
    // ==========================================================================
    // ALB Security Group - CloudFront에서만 접근 허용
    const albSg = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
      vpc,
      description: 'Security group for ALB - CloudFront only',
      allowAllOutbound: true,
    });

    // CloudFront Managed Prefix List를 통해 CloudFront IP 범위만 허용
    const cloudfrontPrefixList = ec2.Peer.prefixList('pl-3b927c52'); // us-east-1
    albSg.addIngressRule(cloudfrontPrefixList, ec2.Port.tcp(80), 'Allow HTTP from CloudFront only');

    // ECS Service Security Group
    const ecsSg = new ec2.SecurityGroup(this, 'EcsSecurityGroup', {
      vpc,
      description: 'Security group for ECS Fargate tasks',
      allowAllOutbound: true,
    });
    ecsSg.addIngressRule(albSg, ec2.Port.tcp(8501), 'Allow Streamlit from ALB');

    // ==========================================================================
    // ECS Cluster
    // ==========================================================================
    const cluster = new ecs.Cluster(this, 'StockAppCluster', {
      vpc,
      clusterName: 'StockAppCluster',
      containerInsights: true,
    });

    // ==========================================================================
    // ECS Task Definition
    // ==========================================================================
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'StockAppTaskDef', {
      memoryLimitMiB: 4096,  // 4GB
      cpu: 2048,             // 2 vCPU
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });

    // Bedrock 접근 권한 추가
    taskDefinition.addToTaskRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
      ],
      resources: ['*'],
    }));

    // CloudWatch Logs 그룹
    const logGroup = new logs.LogGroup(this, 'StockAppLogGroup', {
      logGroupName: '/ecs/stock-app',
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // 컨테이너 정의
    const container = taskDefinition.addContainer('StockAppContainer', {
      image: ecs.ContainerImage.fromEcrRepository(ecrRepository, 'latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'stock-app',
        logGroup,
      }),
      healthCheck: {
        command: ['CMD-SHELL', 'python -c "import urllib.request; urllib.request.urlopen(\'http://localhost:8501/_stcore/health\')" || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        startPeriod: cdk.Duration.seconds(60),
        retries: 3,
      },
    });

    container.addPortMappings({
      containerPort: 8501,
      protocol: ecs.Protocol.TCP,
    });

    // ==========================================================================
    // Application Load Balancer
    // ==========================================================================
    const alb = new elbv2.ApplicationLoadBalancer(this, 'StockAppAlb', {
      vpc,
      internetFacing: true,
      securityGroup: albSg,
    });

    // ALB 액세스 로그 활성화
    alb.logAccessLogs(logBucket, 'alb-logs');

    // ==========================================================================
    // ECS Fargate Service
    // ==========================================================================
    const fargateService = new ecs.FargateService(this, 'StockAppService', {
      cluster,
      taskDefinition,
      serviceName: 'StockAppService',
      desiredCount: 1,
      assignPublicIp: false,
      securityGroups: [ecsSg],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      circuitBreaker: { rollback: true },
      enableExecuteCommand: true,  // ECS Exec 활성화 (디버깅용)
    });

    // ==========================================================================
    // ALB Target Group & Listener
    // ==========================================================================
    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'StockAppTargetGroup', {
      vpc,
      port: 8501,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: '/_stcore/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyHttpCodes: '200',
      },
    });

    // ECS Service를 Target Group에 연결
    fargateService.attachToApplicationTargetGroup(targetGroup);

    // ALB Listener - 커스텀 헤더 검증
    const listener = alb.addListener('HttpListener', {
      port: 80,
      defaultAction: elbv2.ListenerAction.fixedResponse(403, {
        contentType: 'text/plain',
        messageBody: 'Access Denied - Direct access not allowed',
      }),
    });

    // X-Origin-Verify 헤더가 있는 요청만 허용
    listener.addAction('AllowCloudFrontOnly', {
      priority: 1,
      conditions: [
        elbv2.ListenerCondition.httpHeader('X-Origin-Verify', [originVerifySecret.secretValue.unsafeUnwrap()]),
      ],
      action: elbv2.ListenerAction.forward([targetGroup]),
    });

    // ==========================================================================
    // CloudFront Distribution
    // ==========================================================================
    const distribution = new cloudfront.Distribution(this, 'StockAppDistribution', {
      defaultBehavior: {
        origin: new origins.LoadBalancerV2Origin(alb, {
          protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
          customHeaders: {
            'X-Origin-Verify': originVerifySecret.secretValue.unsafeUnwrap(),
          },
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
      },
      enableLogging: true,
      logBucket: logBucket,
      logFilePrefix: 'cloudfront-logs/',
      logIncludesCookies: true,
    });

    // ==========================================================================
    // Auto Scaling (선택적)
    // ==========================================================================
    const scaling = fargateService.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 3,
    });

    scaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // ==========================================================================
    // Outputs
    // ==========================================================================
    new cdk.CfnOutput(this, 'CloudFrontUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'CloudFront URL (Use this URL to access the application)',
    });

    new cdk.CfnOutput(this, 'AlbDnsName', {
      value: alb.loadBalancerDnsName,
      description: 'ALB DNS Name (Do not access directly)',
    });

    new cdk.CfnOutput(this, 'EcrRepositoryUri', {
      value: ecrRepository.repositoryUri,
      description: 'ECR Repository URI',
    });

    new cdk.CfnOutput(this, 'EcsClusterName', {
      value: cluster.clusterName,
      description: 'ECS Cluster Name',
    });

    new cdk.CfnOutput(this, 'EcsServiceName', {
      value: fargateService.serviceName,
      description: 'ECS Service Name',
    });

    new cdk.CfnOutput(this, 'LogBucketName', {
      value: logBucket.bucketName,
      description: 'S3 Bucket for access logs',
    });
  }
}
