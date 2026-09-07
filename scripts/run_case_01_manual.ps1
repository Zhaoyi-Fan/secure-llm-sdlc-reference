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
    throw "Case 1 manual checks are restricted to a loopback BaseUrl."
}

function Invoke-Case1Request {
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

        $status = [int]$_.Exception.Response.StatusCode
        $responseBody = $_.ErrorDetails.Message
        if (-not [string]::IsNullOrWhiteSpace($responseBody)) {
            try {
                $responseBody = $responseBody | ConvertFrom-Json -ErrorAction Stop
            }
            catch {
                # Keep the original response text when it is not JSON.
            }
        }

        return [pscustomobject]@{
            status = $status
            body   = $responseBody
        }
    }
}

function Get-DemoHeaders {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Username
    )

    $login = Invoke-Case1Request -Method Post -Uri "$BaseUrl/login" -Body @{
        username = $Username
        password = "$Username-password"
    }
    if ($login.status -ne 200 -or [string]::IsNullOrWhiteSpace($login.body.access_token)) {
        throw "Login failed for $Username with HTTP $($login.status)."
    }
    return @{ Authorization = "Bearer $($login.body.access_token)" }
}

function Get-FirstPaidOrder {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Orders,

        [Parameter(Mandatory = $true)]
        [string]$Owner
    )

    foreach ($order in $Orders) {
        if ($order.status -eq "paid") {
            return $order
        }
    }
    throw "No paid order was returned for $Owner. Re-seed the demo database and retry."
}

$aliceHeaders = Get-DemoHeaders -Username "alice"
$bobHeaders = Get-DemoHeaders -Username "bob"

$aliceOrdersResult = Invoke-Case1Request -Method Get -Uri "$BaseUrl/orders" -Headers $aliceHeaders
$bobOrdersResult = Invoke-Case1Request -Method Get -Uri "$BaseUrl/orders" -Headers $bobHeaders
if ($aliceOrdersResult.status -ne 200 -or $bobOrdersResult.status -ne 200) {
    throw "Order discovery failed. Alice HTTP $($aliceOrdersResult.status); Bob HTTP $($bobOrdersResult.status)."
}

$aliceOrders = @($aliceOrdersResult.body)
$bobOrders = @($bobOrdersResult.body)
$aliceOrder = Get-FirstPaidOrder -Orders $aliceOrders -Owner "alice"
$bobOrder = Get-FirstPaidOrder -Orders $bobOrders -Owner "bob"

$ownRead = Invoke-Case1Request -Method Get `
    -Uri "$BaseUrl/orders/$($aliceOrder.id)" -Headers $aliceHeaders
$crossRead = Invoke-Case1Request -Method Get `
    -Uri "$BaseUrl/orders/$($bobOrder.id)" -Headers $aliceHeaders
$crossRefund = Invoke-Case1Request -Method Post `
    -Uri "$BaseUrl/orders/$($bobOrder.id)/refund" -Headers $aliceHeaders `
    -Body @{ amount_cents = [int]$bobOrder.amount_cents }
$bobAfter = Invoke-Case1Request -Method Get `
    -Uri "$BaseUrl/orders/$($bobOrder.id)" -Headers $bobHeaders
$ownRefund = Invoke-Case1Request -Method Post `
    -Uri "$BaseUrl/orders/$($aliceOrder.id)/refund" -Headers $aliceHeaders `
    -Body @{ amount_cents = [int]$aliceOrder.amount_cents }

if ($Expected -eq "v0") {
    $passed = (
        $ownRead.status -eq 200 -and
        $ownRefund.status -eq 200 -and
        $crossRead.status -eq 200 -and
        $crossRefund.status -eq 200 -and
        $bobOrder.status -eq "paid" -and
        $bobAfter.status -eq 200 -and
        $bobAfter.body.status -eq "refunded"
    )
}
else {
    $passed = (
        $ownRead.status -eq 200 -and
        $ownRefund.status -eq 200 -and
        $crossRead.status -eq 404 -and
        $crossRefund.status -eq 404 -and
        $bobOrder.status -eq "paid" -and
        $bobAfter.status -eq 200 -and
        $bobAfter.body.status -eq "paid"
    )
}

$summary = [ordered]@{
    schema_version = 1
    expected_snapshot = $Expected
    base_url = $BaseUrl
    positive_control = [ordered]@{
        principal = "alice"
        own_order_id = $aliceOrder.id
        read_http_status = $ownRead.status
        refund_http_status = $ownRefund.status
    }
    cross_customer_attempt = [ordered]@{
        principal = "alice"
        target_owner = "bob"
        target_order_id = $bobOrder.id
        before_order = $bobOrder
        before_status = $bobOrder.status
        read_http_status = $crossRead.status
        read_response = $crossRead.body
        refund_http_status = $crossRefund.status
        refund_response = $crossRefund.body
        after_order = $bobAfter.body
        after_status = $bobAfter.body.status
    }
    expectation_met = $passed
}

$summary | ConvertTo-Json -Depth 8
if (-not $passed) {
    throw "Observed behavior did not match the expected $Expected result. Re-seed the selected snapshot and retry."
}
