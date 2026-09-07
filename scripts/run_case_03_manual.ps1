[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("v0", "v1")]
    [string]$Expected,

    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")
$parsedBaseUrl = [Uri]$BaseUrl
if ($parsedBaseUrl.Scheme -notin @("http", "https") -or -not $parsedBaseUrl.IsLoopback) {
    throw "Case 3 manual checks are restricted to a loopback BaseUrl."
}

function Invoke-Case3Request {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Get", "Post")]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [hashtable]$Headers = @{},

        [object]$Body = $null
    )

    $request = @{
        Method      = $Method
        Uri         = $Uri
        Headers     = $Headers
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $request.ContentType = "application/json"
        $request.Body = $Body | ConvertTo-Json -Depth 6 -Compress
    }

    try {
        $response = Invoke-RestMethod @request
        return [pscustomobject]@{
            status = 200
            body   = $response
        }
    }
    catch {
        if ($null -eq $_.Exception.Response) {
            throw
        }
        return [pscustomobject]@{
            status = [int]$_.Exception.Response.StatusCode
            body   = $_.ErrorDetails.Message
        }
    }
}

function Get-DemoHeaders {
    $login = Invoke-Case3Request -Method Post -Uri "$BaseUrl/login" -Body @{
        username = "alice"
        password = "alice-password"
    }
    if ($login.status -ne 200 -or [string]::IsNullOrWhiteSpace($login.body.access_token)) {
        throw "Login failed for Alice with HTTP $($login.status)."
    }
    return @{ Authorization = "Bearer $($login.body.access_token)" }
}

function Search-KnowledgeBase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Query,

        [Parameter(Mandatory = $true)]
        [hashtable]$Headers
    )

    $encodedQuery = [Uri]::EscapeDataString($Query)
    return Invoke-Case3Request -Method Get `
        -Uri "$BaseUrl/kb?q=$encodedQuery" -Headers $Headers
}

$headers = Get-DemoHeaders
$normal = Search-KnowledgeBase -Query "Refund policy" -Headers $headers
$unionPayload = (
    "unlikely%' UNION SELECT id, username, " +
    "'CASE3_INJECTED_ROW' FROM users -- "
)
$union = Search-KnowledgeBase -Query $unionPayload -Headers $headers
$wildcard = Search-KnowledgeBase -Query "%" -Headers $headers

$normalTitles = @(
    @($normal.body) | ForEach-Object { $_.title }
)
$injectedUsers = @(
    @($union.body) |
        Where-Object {
            $_.body -eq "CASE3_INJECTED_ROW" -and
            $_.title -in @("alice", "bob", "mallory")
        } |
        ForEach-Object { $_.title } |
        Sort-Object -Unique
)
$wildcardResultCount = @($wildcard.body).Count

if ($Expected -eq "v0") {
    $passed = (
        $normal.status -eq 200 -and
        $normalTitles -contains "Refund policy" -and
        $union.status -eq 200 -and
        ($injectedUsers -join ",") -eq "alice,bob,mallory" -and
        $wildcard.status -eq 200 -and
        $wildcardResultCount -gt 0
    )
}
else {
    $passed = (
        $normal.status -eq 200 -and
        $normalTitles -contains "Refund policy" -and
        $union.status -eq 200 -and
        $injectedUsers.Count -eq 0 -and
        $wildcard.status -eq 200 -and
        $wildcardResultCount -eq 0
    )
}

$summary = [ordered]@{
    schema_version = 1
    expected_snapshot = $Expected
    base_url = $BaseUrl
    positive_control = [ordered]@{
        query = "Refund policy"
        http_status = $normal.status
        returned_titles = $normalTitles
    }
    union_injection = [ordered]@{
        http_status = $union.status
        payload_marker = "CASE3_INJECTED_ROW"
        injected_usernames = $injectedUsers
        injected_row_count = $injectedUsers.Count
    }
    like_metacharacter = [ordered]@{
        query = "%"
        http_status = $wildcard.status
        result_count = $wildcardResultCount
    }
    expectation_met = $passed
}

$summary | ConvertTo-Json -Depth 8
if (-not $passed) {
    throw "Observed behavior did not match the expected $Expected result. Re-seed the selected snapshot and retry."
}
