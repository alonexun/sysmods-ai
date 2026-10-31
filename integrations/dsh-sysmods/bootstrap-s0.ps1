﻿﻿﻿# SysMods x DSH —— S0 隔离基线一键搭建
# 依据：主计划 V1.3 §11 S0 / §8.6 DSH 供应链与数据边界
# 用法：powershell -ExecutionPolicy Bypass -File bootstrap-s0.ps1 [-DshRepo <path>] [-DshHome <path>]
# 幂等：重复执行会重建 profile（--from-default-profile 为 create/replace 语义）并重放 patch
param(
  [string]$DshRepo = "C:\Users\Chengzhang XUN\Documents\GITHUB\deepseek-harness",
  [string]$DshHome = "C:\Users\Chengzhang XUN\Documents\DESHY\Hy\Hyapps\Sysmods\dsh-homes\s0"
)

# 注：不用 $ErrorActionPreference=Stop——corepack 会向 stderr 打印命令行 banner，Stop 会误判为错误；
#     所有失败判定走显式退出码检查。
$ErrorActionPreference = "Continue"
$PinnedCommit = "22ddee3792402c3e70ec5f86a63c3e3e895a2f60"   # sysmods-s0-pin @ master, v0.2.1-rc.3

# 0) 版本锁校验：DSH 仓必须停在固定 commit，否则中止（Developer Preview 禁止跟随 master）
$head = (git -C $DshRepo rev-parse HEAD).Trim()
if ($head -ne $PinnedCommit) {
  Write-Error "DSH 仓 commit 已漂移: $head（期望 $PinnedCommit）。按 V1.3 §11：升级必须先在隔离环境重跑 S0，禁止生产直接跟随主分支。"
  exit 1
}

# 1) 隔离 DSH_HOME —— 绝不使用/触碰 ~/.dsh 生产数据（会话/凭据按租户隔离）
New-Item -ItemType Directory -Force -Path $DshHome | Out-Null
$env:DSH_HOME = $DshHome
if ($DshHome -eq "$HOME\.dsh") { Write-Error "禁止使用默认 ~/.dsh 作为 S0 环境"; exit 1 }

Push-Location $DshRepo
try {
  # 2) 从 headless 模板创建 profile
  corepack pnpm dsh --profile sysmods-s0 --from-default-profile headless --dump-config *> $null
  if ($LASTEXITCODE -ne 0) { Write-Error "profile 初始化失败"; exit 1 }

  # 3) 应用 S0 patch：关闭日志上传（session-log-deepseek）+ 遥测导出（session-telemetry-otel）+ Shell（tool-bash/pwsh/jobs）
  $patch = Join-Path $PSScriptRoot "profiles\sysmods-s0.cordis.patch.yml"
  Copy-Item $patch (Join-Path $DshHome "profiles\sysmods-s0\cordis.patch.yml") -Force

  # 4) 生成验证证据（组合后配置 dump）
  corepack pnpm dsh --profile sysmods-s0 --dump-config |
    Out-File (Join-Path $PSScriptRoot "dsh\s0-dump-patched.yml") -Encoding utf8

  Write-Host "S0 环境就绪：DSH_HOME = $DshHome"
  Write-Host "  - 无凭据（$DshHome\.credentials.yaml 不存在，LLM 无法外呼）"
  Write-Host "  - session-log-deepseek: enabled=false；session-telemetry-otel: mode=DISABLED"
  Write-Host "  - tool-bash / tool-pwsh / tool-jobs: disabled=true（Shell 默认禁用）"
  Write-Host "  - 复跑真实任务/接入 key 属 S1 范围，S0 仅验证配置组合"
}
finally { Pop-Location }
