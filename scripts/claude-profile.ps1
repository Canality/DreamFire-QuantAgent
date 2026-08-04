param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('qwen', 'deepseek')]
    [string]$Profile,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

& python (Join-Path $PSScriptRoot 'claude_profile.py') $Profile @ClaudeArgs
exit $LASTEXITCODE
