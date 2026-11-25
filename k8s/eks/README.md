# EKS (4단계) 환경별 파일

공통 매니페스트(`../`)는 그대로 쓰고, EKS에서 달라지는 것만 이 폴더에 둔다.

| 파일 | 내용 |
| --- | --- |
| `storageclass-ebs.yaml` | 기본 StorageClass `ebs` (Auto Mode EBS, gp3) |
| `gateway-alb.yaml` | GatewayClass · LoadBalancerConfiguration(internet-facing) · Gateway · HTTPRoute → ALB |

이미지는 적용할 때 GHCR 경로를 ECR 경로로 바꾼다. 계정 ID는 저장소에 남기지 않는다.

```shell
REG="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-northeast-2.amazonaws.com"
sed -e "s#ghcr.io/seongwb/\(cost-[a-z]*\):[0-9.]*#$REG/\1:2.0#" ../20-was.yaml | kubectl apply -f -
```
