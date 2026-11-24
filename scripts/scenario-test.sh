#!/usr/bin/env bash
# 테스트 시나리오 — ① 로컬 · ② 컨테이너 · ③ Kubernetes · ④ EKS 모든 단계에서 같은 시나리오로 확인한다.
#
#   scripts/scenario-test.sh [BASE_URL]            # S1~S6: 조회 · 등록 · 조회 · 수정 · 오류 처리
#   scripts/scenario-test.sh [BASE_URL] --verify   # S7: 재시작/Pod 교체 후 수정한 값이 남아 있는지
#
# BASE_URL 기본값: http://localhost:8000 (WAS 직접). Web(nginx)을 거치면 http://localhost:8080
set -uo pipefail

BASE="${1:-http://localhost:8000}"
MODE="${2:-}"
SERVICE="scenario-test"          # 시나리오 전용 예산 항목 (실제 서비스명과 겹치지 않게)
MONTH="2026-11"
CREATED_AMOUNT=100
UPDATED_AMOUNT=150.5

pass=0; fail=0
ok()  { printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass + 1)); }
ng()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail + 1)); }
check() { if [[ "$2" == "$3" ]]; then ok "$1"; else ng "$1 (기대: $3, 실제: $2)"; fi; }

# 응답 본문은 $BODY, 상태 코드는 $CODE 에 담는다
call() {
  local method="$1" path="$2" data="${3:-}"
  local out
  if [[ -n "$data" ]]; then
    out=$(curl -s -w '\n%{http_code}' -X "$method" -H 'Content-Type: application/json' -d "$data" "$BASE$path")
  else
    out=$(curl -s -w '\n%{http_code}' -X "$method" "$BASE$path")
  fi
  CODE="${out##*$'\n'}"
  BODY="${out%$'\n'*}"
}
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" <<<"$BODY"; }

find_budget_id() {
  call GET "/api/budgets?month=$MONTH"
  json "next((b['id'] for b in d if b['service']=='$SERVICE'), '')"
}

echo "대상: $BASE"

if [[ "$MODE" == "--verify" ]]; then
  echo "[S7] 데이터 유지 확인 (재시작 · Pod 교체 후)"
  id=$(find_budget_id)
  if [[ -z "$id" ]]; then
    ng "예산 '$SERVICE' 이 남아 있음 (없음)"
  else
    call GET "/api/budgets/$id"
    check "예산 '$SERVICE' 이 남아 있음 (id=$id)" "$CODE" "200"
    check "수정한 금액($UPDATED_AMOUNT)이 유지됨" "$(json "d['amount'] == $UPDATED_AMOUNT")" "True"
  fi
  call GET /api/meta
  [[ "$(json "d['latest_date']")" != "None" ]] && ok "수집된 비용 데이터가 남아 있음" || ng "수집된 비용 데이터 없음"
  echo "결과: $pass passed, $fail failed"
  exit $((fail > 0))
fi

echo "[S1] 상태 확인"
call GET /healthz;  check "GET /healthz → 200" "$CODE" "200"
call GET /readyz;   check "GET /readyz → 200 (DB 연결)" "$CODE" "200"

echo "[S2] 비용 조회"
call GET /api/meta
latest=$(json "d['latest_date']")
[[ "$latest" != "None" ]] && ok "최신 수집일 있음 ($latest)" || ng "수집된 데이터 없음 → collector 먼저 실행"
call GET "/api/costs/daily?date=$latest"
check "GET /api/costs/daily → 200" "$CODE" "200"
# 서비스별 금액과 총액을 각각 소수 둘째 자리로 반올림하므로, 항목당 최대 0.005의 오차가 쌓일 수 있다
check "일일 총액 ≈ 서비스별 합계 (반올림 오차 허용)" "$(json "abs(d['total'] - sum(s['amount'] for s in d['services'])) <= 0.005 * (len(d['services']) + 1) + 1e-9")" "True"

echo "[S3] 예산 등록 (POST)"
old=$(find_budget_id)
if [[ -n "$old" ]]; then
  echo "  (이전 실행에서 등록된 '$SERVICE' id=$old 가 있어 등록 대신 금액을 $CREATED_AMOUNT 로 되돌림)"
  call PUT "/api/budgets/$old" "{\"amount\": $CREATED_AMOUNT}"
  check "기존 예산 되돌리기 → 200" "$CODE" "200"
  id="$old"
else
  call POST /api/budgets "{\"month\":\"$MONTH\",\"service\":\"$SERVICE\",\"amount\":$CREATED_AMOUNT}"
  check "POST /api/budgets → 201" "$CODE" "201"
  id=$(json "d['id']")
fi

echo "[S4] 예산 조회 (GET)"
call GET "/api/budgets/$id"
check "GET /api/budgets/$id → 200" "$CODE" "200"
check "등록한 금액 = $CREATED_AMOUNT" "$(json "d['amount'] == $CREATED_AMOUNT")" "True"
call GET "/api/budgets?month=$MONTH"
check "월 목록에 포함" "$(json "any(b['id']==$id for b in d)")" "True"

echo "[S5] 예산 수정 (PUT)"
call PUT "/api/budgets/$id" "{\"amount\": $UPDATED_AMOUNT}"
check "PUT /api/budgets/$id → 200" "$CODE" "200"
call GET "/api/budgets/$id"
check "다시 조회한 금액 = $UPDATED_AMOUNT" "$(json "d['amount'] == $UPDATED_AMOUNT")" "True"

echo "[S6] 오류 처리"
call POST /api/budgets "{\"month\":\"$MONTH\",\"service\":\"$SERVICE\",\"amount\":1}"
check "같은 월 · 서비스 중복 등록 → 409" "$CODE" "409"
call POST /api/budgets "{\"month\":\"2026-13\",\"service\":\"x\",\"amount\":-1}"
check "잘못된 입력 → 422" "$CODE" "422"
call GET /api/budgets/999999
check "없는 예산 → 404" "$CODE" "404"

echo "결과: $pass passed, $fail failed"
exit $((fail > 0))
