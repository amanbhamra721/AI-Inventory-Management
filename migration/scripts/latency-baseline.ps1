param(
    [string]$BaseUrl = "https://your-current-domain.com",
    [string]$ApiHealthPath = "/health",
    [int]$Runs = 10
)

function Measure-Endpoint {
    param(
        [string]$Url,
        [int]$Count
    )

    $results = @()
    for ($i = 1; $i -le $Count; $i++) {
        $output = curl.exe -s -o NUL -w "`%{time_namelookup},`%{time_connect},`%{time_starttransfer},`%{time_total}" $Url
        $parts = $output.Split(",")
        $results += [PSCustomObject]@{
            Run = $i
            DNS = [double]$parts[0]
            Connect = [double]$parts[1]
            TTFB = [double]$parts[2]
            Total = [double]$parts[3]
        }
    }
    return $results
}

function Get-Percentile {
    param(
        [double[]]$Values,
        [double]$Percentile
    )

    $sorted = $Values | Sort-Object
    $index = [Math]::Ceiling($Percentile * $sorted.Count) - 1
    if ($index -lt 0) { $index = 0 }
    return $sorted[$index]
}

$homeUrl = "$BaseUrl/"
$healthUrl = "$BaseUrl$ApiHealthPath"

Write-Host "Measuring: $homeUrl"
$home = Measure-Endpoint -Url $homeUrl -Count $Runs

Write-Host "Measuring: $healthUrl"
$api = Measure-Endpoint -Url $healthUrl -Count $Runs

$report = [PSCustomObject]@{
    TimestampUtc = (Get-Date).ToUniversalTime().ToString("s") + "Z"
    HomeP50 = Get-Percentile -Values $home.Total -Percentile 0.50
    HomeP95 = Get-Percentile -Values $home.Total -Percentile 0.95
    ApiP50 = Get-Percentile -Values $api.Total -Percentile 0.50
    ApiP95 = Get-Percentile -Values $api.Total -Percentile 0.95
}

$report | Format-List

Write-Host "\nRaw Home Results:"
$home | Format-Table -AutoSize

Write-Host "\nRaw API Results:"
$api | Format-Table -AutoSize
