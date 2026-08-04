param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

& (Join-Path $PSScriptRoot 'claude-profile.ps1') deepseek @ClaudeArgs
exit $LASTEXITCODE
