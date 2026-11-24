"""헬스체크 API — 컨테이너 헬스체크용."""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.repositories.cost_repository import CostRepository


class HealthController:
    def __init__(self, repository: CostRepository) -> None:
        self._repo = repository
        self.router = APIRouter(tags=["health"])
        self.router.add_api_route("/healthz", self.healthz, methods=["GET"])
        self.router.add_api_route("/readyz", self.readyz, methods=["GET"])

    def healthz(self) -> dict:
        """liveness: 프로세스가 살아 있는가 (외부 의존성 확인 X)."""
        return {"status": "ok"}

    def readyz(self, response: Response) -> dict:
        """readiness: 요청을 받을 준비가 됐는가 (DB 연결 확인)."""
        if self._repo.ping():
            return {"status": "ready"}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "db unavailable"}
