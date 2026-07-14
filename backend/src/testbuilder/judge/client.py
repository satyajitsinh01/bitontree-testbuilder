"""Code execution boundary (research R1). Judge0 CE when TB_JUDGE0_URL is set;
otherwise a stub that fails closed. Candidate code never executes in the API
process (Constitution IV)."""

import asyncio
import base64
from dataclasses import dataclass

import httpx
import structlog

from ..config import get_settings

log = structlog.get_logger()

JUDGE0_LANGUAGE_IDS = {
    "javascript": 63,  # Node.js
    "python": 71,  # Python 3
    "java": 62,
    "cpp": 54,  # C++ (GCC)
    "c": 50,
}


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    status: str  # completed | compile_error | runtime_error | timeout | failed
    stdout: str
    stderr: str
    time_ms: int
    memory_kb: int


def _truncate(text: str | None, limit: int = 2000) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "…[truncated]"


def map_judge0_status(status_id: int) -> tuple[str, bool]:
    """Judge0 status ids -> (our status, passed)."""
    if status_id == 3:
        return "completed", True
    if status_id == 4:
        return "completed", False  # wrong answer
    if status_id == 5:
        return "timeout", False
    if status_id == 6:
        return "compile_error", False
    if status_id in (7, 8, 9, 10, 11, 12):
        return "runtime_error", False
    return "failed", False


class Judge0Client:
    def __init__(self, base_url: str, auth_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Auth-Token": auth_token} if auth_token else {}

    async def run_case(
        self,
        language: str,
        source: str,
        case: dict,
    ) -> CaseResult:
        language_id = JUDGE0_LANGUAGE_IDS.get(language)
        if language_id is None:
            return CaseResult(
                case["id"], False, "failed", "", f"unsupported language {language}", 0, 0
            )
        payload = {
            "language_id": language_id,
            "source_code": base64.b64encode(source.encode()).decode(),
            "stdin": base64.b64encode(str(case.get("input", "")).encode()).decode(),
            "expected_output": base64.b64encode(
                str(case.get("expected_output", "")).encode()
            ).decode(),
            "cpu_time_limit": min(case.get("time_limit_ms", 5000) / 1000, 15),
            "memory_limit": min(case.get("memory_limit_kb", 128000), 512000),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/submissions?base64_encoded=true&wait=true",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
        status, passed = map_judge0_status(data.get("status", {}).get("id", 13))
        stdout = base64.b64decode(data.get("stdout") or "").decode(errors="replace")
        stderr = base64.b64decode(
            data.get("stderr") or data.get("compile_output") or ""
        ).decode(errors="replace")
        return CaseResult(
            case_id=case["id"],
            passed=passed,
            status=status,
            stdout=_truncate(stdout),
            stderr=_truncate(stderr),
            time_ms=int(float(data.get("time") or 0) * 1000),
            memory_kb=int(data.get("memory") or 0),
        )

    async def run_cases(self, language: str, source: str, cases: list[dict]) -> list[CaseResult]:
        return list(await asyncio.gather(*(self.run_case(language, source, c) for c in cases)))


class StubRunner:
    """Fails closed when no execution backend is configured — never executes
    candidate code in-process."""

    async def run_cases(self, language: str, source: str, cases: list[dict]) -> list[CaseResult]:
        return [
            CaseResult(
                case_id=c["id"],
                passed=False,
                status="failed",
                stdout="",
                stderr="code execution backend not configured (set TB_JUDGE0_URL)",
                time_ms=0,
                memory_kb=0,
            )
            for c in cases
        ]


_runner_override = None


def set_runner_for_tests(runner) -> None:
    global _runner_override
    _runner_override = runner


def get_runner():
    if _runner_override is not None:
        return _runner_override
    settings = get_settings()
    if settings.judge0_url:
        return Judge0Client(settings.judge0_url, settings.judge0_auth_token)
    return StubRunner()
