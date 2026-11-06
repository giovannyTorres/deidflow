from __future__ import annotations

import hashlib
import json

import pytest

RESPONSE = 'print(\'{"status":"COMPLETED","counts":{"completed_documents":1}}\')\n'


def run_case(tmp_path, code=RESPONSE, **kwargs):
    from deidflow.benchmarks.isolation import run_isolated_case

    script = tmp_path / "FICTIONAL_PRIVATE_FILENAME.py"
    script.write_text(code)
    kwargs.setdefault("reference_root", tmp_path / "reference")
    return run_isolated_case(
        script,
        script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        input_payload={"text": "Texto ficticio de ejercicio"},
        case_id="c-a",
        required_mentions=3,
        output=tmp_path / "report",
        **kwargs,
    )["result"]


def require_native(result):
    if result["status"] == "UNSUPPORTED":
        assert result["strict_custody_accredited"] is False
        pytest.skip("Native isolation unavailable; product fails closed")


def test_actual_native_case_completes_without_external_access(tmp_path):
    result = run_case(tmp_path)
    require_native(result)
    assert result["status"] == "COMPLETED"
    assert result["network_attempts"] == 0
    assert result["strict_custody_accredited"] is True
    assert result["limits"]["hard_memory_kind"] == "RLIMIT_AS_ADDRESS_SPACE"
    assert result["required_support"] == {"documents": 1, "mentions": 3}


@pytest.mark.parametrize("mode", ["python", "native", "subprocess"])
def test_network_attempts_fail_even_when_exception_is_caught(tmp_path, mode):
    code = {
        "python": 'import socket\ntry:\n socket.create_connection(("127.0.0.1",9), timeout=.1)\nexcept OSError:\n pass\n',
        "native": "import ctypes\nlibc=ctypes.CDLL(None)\nlibc.close(libc.socket(2,1,0))\n",
        "subprocess": 'import subprocess,sys\nsubprocess.run([sys.executable,"-c","import socket; socket.socket()"],capture_output=True)\n',
    }[mode]
    result = run_case(tmp_path, code + RESPONSE)
    require_native(result)
    assert result["network_attempts"] > 0
    assert result["status"] == "LOCAL_POLICY_VIOLATION"
    assert result["strict_custody_accredited"] is False


def test_reference_outside_mounted_inputs_is_really_inaccessible(tmp_path):
    secret = tmp_path / "FICTIONAL_GOLD_CANARY.txt"
    secret.write_text("FICTIONAL_GOLD_CANARY")
    code = (
        f'from pathlib import Path\ntry:\n Path({str(secret)!r}).read_text()\nexcept OSError:\n pass\nelse:\n raise RuntimeError("GOLD_WAS_ACCESSIBLE")\n'
        + RESPONSE
    )
    result = run_case(tmp_path, code, reference_root=tmp_path)
    require_native(result)
    assert result["status"] == "COMPLETED"
    assert result["strict_custody_accredited"] is True
    assert "FICTIONAL_GOLD" not in (tmp_path / "report" / "report.json").read_text()


def test_timeout_does_not_drop_required_case_or_mentions(tmp_path):
    from deidflow.benchmarks.isolation import IsolationLimits

    result = run_case(
        tmp_path,
        "import time\ntime.sleep(10)\n" + RESPONSE,
        limits=IsolationLimits(wall_seconds=0.2),
    )
    require_native(result)
    assert result["status"] == "TIMEOUT"
    assert result["required_support"] == {"documents": 1, "mentions": 3}
    assert result["counts"] is None


def test_hard_memory_limit_is_not_just_admission_metadata(tmp_path):
    from deidflow.benchmarks.isolation import IsolationLimits

    code = "try:\n data=bytearray(512*1024*1024)\nexcept MemoryError:\n pass\n" + RESPONSE
    result = run_case(tmp_path, code, limits=IsolationLimits(memory_bytes=64 * 1024 * 1024))
    require_native(result)
    assert result["status"] == "RESOURCE_LIMIT"
    assert result["memory_limit_events"] > 0


def test_admission_expansion_limit_is_explicit_and_keeps_support(tmp_path):
    result = run_case(tmp_path, expanded_bytes=100_000_000)
    assert result["status"] == "ADMISSION_LIMIT"
    assert result["counts"] is None
    assert result["required_support"]["mentions"] == 3
    assert result["strict_custody_accredited"] is False


def test_missing_asset_is_not_downloaded_or_hidden(tmp_path):
    from deidflow.benchmarks.isolation import LocalAsset

    result = run_case(tmp_path, assets=(LocalAsset("asset-a", tmp_path / "missing", "0" * 64),))
    assert result["status"] == "MISSING_ASSET"
    assert result["required_support"]["mentions"] == 3


def test_canaries_stdout_stderr_filename_and_environment_do_not_enter_summary(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FICTIONAL_SECRET", "FICTIONAL_ENV_CANARY")
    code = 'import os,sys\nassert "FICTIONAL_SECRET" not in os.environ\nprint("FICTIONAL_BODY_CANARY")\nraise RuntimeError("FICTIONAL_EXCEPTION_CANARY")\n'
    result = run_case(tmp_path, code)
    require_native(result)
    assert result["status"] == "CANDIDATE_ERROR"
    serialized = (tmp_path / "report" / "report.json").read_text()
    assert not any(
        canary in serialized
        for canary in (
            "FICTIONAL_BODY",
            "FICTIONAL_ENV",
            "FICTIONAL_EXCEPTION",
            "FICTIONAL_PRIVATE_FILENAME",
        )
    )
    assert json.loads(serialized)["result"]["required_support"]["mentions"] == 3


def test_missing_native_capability_fails_closed(tmp_path, monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = run_case(tmp_path)
    assert result["status"] == "UNSUPPORTED"
    assert result["strict_custody_accredited"] is False
    assert result["required_support"]["mentions"] == 3


def test_malformed_successful_response_never_exposes_its_content(tmp_path):
    result = run_case(
        tmp_path, 'print(\'{"status":"COMPLETED","secret":"FICTIONAL_BODY_CANARY"}\')\n'
    )
    require_native(result)
    assert result["status"] == "MALFORMED_RESPONSE"
    assert result["counts"] is None
    assert "FICTIONAL_BODY" not in (tmp_path / "report" / "report.json").read_text()


def test_undeclared_reference_boundary_cannot_accredit_strict_custody(tmp_path):
    result = run_case(tmp_path, reference_root=None)
    require_native(result)
    assert result["status"] == "COMPLETED"
    assert result["strict_custody_accredited"] is False
    assert result["reference_boundary_declared"] is False


def test_untraced_clone_cannot_accredit_native_audit(tmp_path):
    import platform

    if platform.machine() != "x86_64":
        pytest.skip("Raw clone probe is x86_64-specific")
    code = (
        """import ctypes,os
libc=ctypes.CDLL(None)
libc.syscall.restype=ctypes.c_long
pid=libc.syscall(56,ctypes.c_ulong(17|0x00800000),0,0,0,0)
if pid==0:
 libc.close(libc.socket(2,1,0))
 os._exit(0)
if pid>0:
 os.waitpid(pid,0)
"""
        + RESPONSE
    )
    result = run_case(tmp_path, code)
    require_native(result)
    assert result["status"] == "LOCAL_POLICY_VIOLATION"
    assert result["capabilities"]["native_syscall_audit"] is False
    assert result["strict_custody_accredited"] is False
    assert result["audit_integrity_events"] > 0


def test_deep_candidate_json_is_not_a_dataset_failure(tmp_path):
    result = run_case(tmp_path, 'print("["*50000+"0"+"]"*50000)\n')
    require_native(result)
    assert result["status"] == "MALFORMED_RESPONSE"
    assert result["required_support"]["mentions"] == 3


def test_lower_inherited_hard_limit_keeps_a_sanitized_report(tmp_path):
    import subprocess
    import sys

    script = tmp_path / "program.py"
    script.write_text(RESPONSE)
    code = """import hashlib,json,resource,sys
from pathlib import Path
from deidflow.benchmarks.isolation import run_isolated_case
root=Path(sys.argv[1])
program=root/'program.py'
resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
result=run_isolated_case(program,script_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),input_payload={},case_id='c-a',required_mentions=3,output=root/'report',reference_root=root/'reference')
print(json.dumps(result))
"""
    process = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], capture_output=True, timeout=10
    )
    assert process.returncode == 0
    result = json.loads(process.stdout)["result"]
    assert result["required_support"]["mentions"] == 3
    assert result["status"] in {"COMPLETED", "UNSUPPORTED"}
