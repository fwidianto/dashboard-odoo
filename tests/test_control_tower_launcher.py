from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = (ROOT / "scripts" / "start-control-tower.ps1").read_text(encoding="utf-8")
STOP = (ROOT / "scripts" / "stop-control-tower.ps1").read_text(encoding="utf-8")
INSTALL = (ROOT / "scripts" / "install-control-tower-shortcut.ps1").read_text(encoding="utf-8")


def test_launcher_uses_required_interpreter_env_and_read_only_health() -> None:
    assert "dashboard-odoo'" in START
    assert "venv\\Scripts\\python.exe" in START
    assert "Join-Path $configurationRepository '.env'" in START
    assert ".env.sandbox" not in START
    for variable in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        assert variable in START
    assert "/control-tower/health" in START
    assert "--env-file" in START
    assert "src.api:app" in START
    assert "WindowStyle Hidden" in START
    assert "run_incremental_sync" not in START
    assert "run_control_tower_refresh" not in START


def test_launcher_reuses_health_and_handles_port_collision_without_termination() -> None:
    assert "reused-launcher-process" in START
    assert "reused-external-control-tower" in START
    assert "fallback non-destruktif" in START
    collision_section = START[START.index("if (Test-TcpEndpoint -HostName '127.0.0.1'") :]
    assert "Stop-Process" not in collision_section.split("$serverProcess = Start-Process", 1)[0]
    assert "--app=$url" in START
    assert "Start-Process $url" in START
    assert "if ($PreferredPort -lt 65535)" in START


def test_launcher_retains_ownership_state_when_identity_is_inconclusive() -> None:
    assert "Status = 'inconclusive'" in START
    identity_guard = START.index("if ($processState.Status -eq 'inconclusive')")
    stale_removal = START.index("Remove-Item -LiteralPath $pidPath -Force", identity_guard)
    assert identity_guard < stale_removal
    assert "State launcher dipertahankan" in START[identity_guard:stale_removal]
    assert "health-timeout-identity-inconclusive" in START


def test_stop_script_verifies_pid_identity_before_stopping() -> None:
    stop_position = STOP.index("Stop-Process -Id $process.Id")
    assert STOP.index("$process.Path -eq $pythonPath") < stop_position
    assert STOP.index("$process.StartTime") < stop_position
    assert STOP.index("Get-CimInstance Win32_Process") < stop_position
    assert STOP.index("src\\.api:app") < stop_position
    assert "PID sekarang dimiliki proses lain" in STOP


def test_shortcut_contains_no_secret_arguments() -> None:
    assert "Control Tower.lnk" in INSTALL
    assert "start-control-tower.cmd" in INSTALL
    assert "POSTGRES_" not in INSTALL
    assert ".Arguments" not in INSTALL
    assert (ROOT / "start-control-tower.cmd").is_file()
    assert (ROOT / "stop-control-tower.cmd").is_file()
