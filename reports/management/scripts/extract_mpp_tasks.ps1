<#
.SYNOPSIS
  Extracts every task's schedule data (dates, duration, total slack,
  critical flag, predecessors) from a Microsoft Project (.mpp) file into
  a JSON file, for import_ms_project_schedule's --json option.

  On this machine, launching Microsoft Project via COM from Python
  (win32com) fails with "Server execution failed" -- PowerShell's
  New-Object -ComObject does not have this problem, so this script is
  the reliable extraction path; import_ms_project_schedule's --mpp
  option (direct Python COM) is kept as a convenience for environments
  where it does work, but --json fed by this script is what's actually
  been verified to work here.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File extract_mpp_tasks.ps1 `
      -MppPath "C:\path\to\schedule.mpp" -OutJson "C:\path\to\tasks.json"

  python manage.py import_ms_project_schedule --project TAB --json "C:\path\to\tasks.json"
#>
param(
    [Parameter(Mandatory=$true)][string]$MppPath,
    [Parameter(Mandatory=$true)][string]$OutJson
)

$ErrorActionPreference = "Stop"

$app = New-Object -ComObject MSProject.Application
$app.Visible = $false
$app.DisplayAlerts = $false

try {
    $app.FileOpen($MppPath)
    $proj = $app.ActiveProject

    $rows = @()
    foreach ($t in $proj.Tasks) {
        if ($null -eq $t) { continue }
        $rows += [PSCustomObject]@{
            ID              = $t.ID
            UniqueID        = $t.UniqueID
            Name            = $t.Name
            OutlineLevel    = $t.OutlineLevel
            Summary         = $t.Summary
            Milestone       = $t.Milestone
            Start           = if ($t.Start) { $t.Start.ToString("yyyy-MM-dd") } else { $null }
            Finish          = if ($t.Finish) { $t.Finish.ToString("yyyy-MM-dd") } else { $null }
            Duration        = $t.Duration
            DurationText    = $t.DurationText
            PercentComplete = $t.PercentComplete
            TotalSlack      = $t.TotalSlack
            Critical        = $t.Critical
            Predecessors    = $t.Predecessors
            ResourceNames   = $t.ResourceNames
        }
    }

    $rows | ConvertTo-Json -Depth 5 | Out-File -FilePath $OutJson -Encoding utf8
    Write-Output "Extracted $($rows.Count) tasks to $OutJson"
} finally {
    try { $proj.Close(0) } catch {}   # 0 = pjDoNotSave
    try { $app.Quit() } catch {}
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($app) | Out-Null
}
