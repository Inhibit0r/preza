param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$app = $null
$deck = $null
$ownsApp = $false
$oldSecurity = $null
try {
    try { $app = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application') }
    catch { $app = New-Object -ComObject PowerPoint.Application; $ownsApp = $true }
    $oldSecurity = $app.AutomationSecurity
    $app.AutomationSecurity = 3 # Disable macros while opening the input.
    $deck = $app.Presentations.Open($InputPath, -1, 0, 0)
    $count = $deck.Slides.Count
    $hiddenCount = 0
    # This Office build ignores PrintHiddenSlides; unhide only the read-only in-memory deck.
    for ($i = 1; $i -le $count; $i++) {
        if ($deck.Slides.Item($i).SlideShowTransition.Hidden -ne 0) {
            $deck.Slides.Item($i).SlideShowTransition.Hidden = 0
            $hiddenCount++
        }
    }
    # PowerShell's COM binder rejects a null PrintRange; pass the complete range.
    $range = $deck.PrintOptions.Ranges.Add(1, $count)
    $deck.PrintOptions.PrintHiddenSlides = -1
    $deck.ExportAsFixedFormat($OutputPath, 2, 2, 0, 1, 1, -1, $range, 1, '', $false, $true, $true, $false, $false)
    if (-not (Test-Path -LiteralPath $OutputPath) -or (Get-Item -LiteralPath $OutputPath).Length -eq 0) {
        throw 'PowerPoint did not create a nonempty PDF.'
    }
    @{slides=$count; originally_hidden=$hiddenCount; powerpoint_version=$app.Version} | ConvertTo-Json -Compress
}
finally {
    if ($null -ne $deck) {
        try { $deck.Saved = -1; $deck.Close() } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) }
    }
    if ($null -ne $app) {
        if ($null -ne $oldSecurity) { $app.AutomationSecurity = $oldSecurity }
        if ($ownsApp -and $app.Presentations.Count -eq 0) { $app.Quit() }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    }
}
