"""清理重复拉起的 MCP 常驻进程。

宿主每轮工具调用都会重新拉起一批 `core.mcp.*` 进程，旧进程的 stdin 一直没有关闭，
收不到 EOF 就不会退出，只会白占内存。

**只能在宿主导出后运行**：从进程外部无法区分"宿主正在用的连接"和"泄漏的连接"，
会话中结束进程会打断当前工具调用。脚本检测到宿主仍在运行时默认拒绝执行。

用法：
    python ops/clean_mcp_processes.py              # 宿主关闭后清理全部残留进程
    python ops/clean_mcp_processes.py --keep 2     # 每个服务保留最新 2 个
    python ops/clean_mcp_processes.py --force      # 宿主仍在运行时强制清理（会断连）
    python ops/clean_mcp_processes.py --dry-run    # 只报告不结束进程
"""

import argparse
import json
import subprocess

# 这些进程存活时说明会话仍在进行，清理会打断连接
_HOST_PROCESSES = ("WorkBuddy.exe", "codex.exe")

# PowerShell 负责枚举与结束进程；结束前采样一秒 CPU，正在服务的进程不动
_WORKER = r"""
$rows = @()
foreach ($p in (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*core.mcp.*' })) {
    if ($p.CommandLine -notmatch 'core\.mcp\.([a-z_]+)') { continue }
    $module = $matches[1]
    $process = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $rows += [pscustomobject]@{
        Id = $p.ProcessId; Module = $module; Start = $p.CreationDate;
        Cpu = $process.CPU; MemMb = [math]::Round($process.WorkingSet64 / 1MB)
    }
}
$keepIds = @()
foreach ($group in ($rows | Group-Object Module)) {
    $keepIds += ($group.Group | Sort-Object Start -Descending | Select-Object -First $env:MCP_KEEP).Id
}
Start-Sleep -Milliseconds 1000
$killed = @()
foreach ($row in $rows) {
    if ($keepIds -contains $row.Id) { continue }
    $after = Get-Process -Id $row.Id -ErrorAction SilentlyContinue
    if (-not $after) { continue }
    if (($after.CPU - $row.Cpu) -gt 0.1) { continue }
    if ($env:MCP_DRY_RUN -ne '1') { Stop-Process -Id $row.Id -Force -ErrorAction SilentlyContinue }
    $killed += [pscustomobject]@{ Id = $row.Id; Module = $row.Module; MemMb = $row.MemMb }
}
[pscustomobject]@{
    total = $rows.Count
    kept = ($rows | Where-Object { $keepIds -contains $_.Id } | ForEach-Object { $_.Module + '(' + $_.Id + ',' + $_.MemMb + 'MB)' })
    killed = $killed
} | ConvertTo-Json -Depth 4 -Compress
"""


def clean(keep: int, dry_run: bool) -> dict:
    """调用 PowerShell 清理，返回清理结果。"""
    env = {"MCP_KEEP": str(keep), "MCP_DRY_RUN": "1" if dry_run else "0"}
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", f"$env:MCP_KEEP='{keep}'; $env:MCP_DRY_RUN='{env['MCP_DRY_RUN']}'; {_WORKER}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PowerShell 执行失败")
    return json.loads(completed.stdout.strip())


def _host_running() -> list[str]:
    """返回仍在运行的宿主进程名。"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "Get-Process | Where-Object { @('WorkBuddy.exe','codex.exe') -contains ($_.Name + '.exe') } | Select-Object -ExpandProperty Name -Unique"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="清理重复拉起的 MCP 常驻进程")
    parser.add_argument("--keep", type=int, default=1, help="每个服务保留最新几个进程")
    parser.add_argument("--force", action="store_true", help="宿主仍在运行时强制清理，会打断当前连接")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不结束进程")
    args = parser.parse_args()

    hosts = _host_running()
    if hosts and not args.force and not args.dry_run:
        print(f"宿主仍在运行（{'、'.join(hosts)}），清理会打断当前工具连接。请退出宿主后再执行，或加 --force 强制清理。")
        return

    result = clean(args.keep, args.dry_run)
    killed = result.get("killed") or []
    freed = sum(row["MemMb"] for row in killed)
    print(f"扫描 {result.get('total', 0)} 个 MCP 进程，保留：{'、'.join(result.get('kept') or []) or '无'}")
    print(f"{'将结束' if args.dry_run else '已结束'} {len(killed)} 个空闲进程，释放约 {freed} MB")
    for row in killed:
        print(f"  {row['Module']} PID {row['Id']}  {row['MemMb']} MB")


if __name__ == "__main__":
    main()
