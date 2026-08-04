param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

& (Join-Path $PSScriptRoot 'claude-profile.ps1') qwen @ClaudeArgs
exit $LASTEXITCODE
