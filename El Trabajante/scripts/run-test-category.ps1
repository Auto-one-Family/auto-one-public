# ESP32 Test Category Runner
# Runs tests ONE FILE AT A TIME to avoid PlatformIO multiple-definition errors
#
# Usage: .\run-test-category.ps1 -Category <category>
#        .\run-test-category.ps1 -TestFile <filename>
# Categories: actuator, sensor, comm, infra, integration, all

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("actuator", "sensor", "comm", "infra", "integration", "all")]
    [string]$Category,

    [Parameter(Mandatory=$false)]
    [string]$TestFile,

    [Parameter(Mandatory=$false)]
    [string]$Environment = "esp32_dev"
)

# Validate parameters
if (-not $Category -and -not $TestFile) {
    Write-Host "[ERROR] Must specify either -Category or -TestFile" -ForegroundColor Red
    exit 1
}

if ($Category -and $TestFile) {
    Write-Host "[ERROR] Cannot specify both -Category and -TestFile" -ForegroundColor Red
    exit 1
}

# Constants
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$TestDir = Join-Path $ProjectRoot "test"
$ArchiveDir = Join-Path $TestDir "_archive"
$LogFile = Join-Path $TestDir "test_output.log"

# Category prefix mapping
$CategoryPrefixes = @{
    "actuator" = "actuator_"
    "sensor" = "sensor_"
    "comm" = "comm_"
    "infra" = "infra_"
    "integration" = "integration_"
}

# Color output functions
function Write-Success { param($Message) Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-ErrorMsg { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-WarningMsg { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }

# Setup archive directory
function Initialize-Archive {
    if (-not (Test-Path $ArchiveDir)) {
        New-Item -Path $ArchiveDir -ItemType Directory | Out-Null
        Write-Info "Created archive directory"
    }
}

# Move all test .cpp files to archive
function Move-AllTestsToArchive {
    $testFiles = Get-ChildItem -Path $TestDir -Filter "*.cpp" -File

    foreach ($file in $testFiles) {
        $destPath = Join-Path $ArchiveDir $file.Name
        Move-Item -Path $file.FullName -Destination $destPath -Force
    }

    if ($testFiles.Count -gt 0) {
        Write-Info "Archived $($testFiles.Count) test files"
    }
}

# Restore single test file
function Restore-SingleTest {
    param([string]$FileName)

    $sourcePath = Join-Path $ArchiveDir $FileName
    if (-not (Test-Path $sourcePath)) {
        Write-WarningMsg "Test file not found in archive: $FileName"
        return $false
    }

    $destPath = Join-Path $TestDir $FileName
    Copy-Item -Path $sourcePath -Destination $destPath -Force
    return $true
}

# Run PlatformIO tests for single file
function Invoke-SingleTest {
    param([string]$TestName)

    # Change to project root
    Push-Location $ProjectRoot

    try {
        # Run tests and capture output
        $pioCommand = "~/.platformio/penv/Scripts/platformio.exe"
        $output = & $pioCommand test -e $Environment 2>&1 | Tee-Object -FilePath $LogFile -Append

        # Check for failures (look for PASS/FAIL in output)
        $failLines = $output | Select-String ":FAIL"
        $passLines = $output | Select-String ":PASS"
        $ignoreLines = $output | Select-String ":IGNORE"

        $failCount = ($failLines | Measure-Object).Count
        $passCount = ($passLines | Measure-Object).Count
        $ignoreCount = ($ignoreLines | Measure-Object).Count

        # Also check for build errors
        $buildErrors = $output | Select-String "ERROR|Error|error:"
        $hasCompileError = ($buildErrors | Measure-Object).Count -gt 0

        if ($hasCompileError -and $passCount -eq 0) {
            Write-ErrorMsg "  Build failed for $TestName"
            return $false
        }

        if ($failCount -gt 0) {
            Write-ErrorMsg "  $TestName : $failCount FAIL, $passCount PASS, $ignoreCount IGNORE"
            return $false
        } else {
            Write-Success "  $TestName : $passCount PASS, $ignoreCount IGNORE"
            return $true
        }
    }
    catch {
        Write-ErrorMsg "Test execution failed: $_"
        return $false
    }
    finally {
        Pop-Location
    }
}

# Cleanup: Move test back to archive
function Cleanup-SingleTest {
    param([string]$FileName)

    $testPath = Join-Path $TestDir $FileName
    if (Test-Path $testPath) {
        $destPath = Join-Path $ArchiveDir $FileName
        Move-Item -Path $testPath -Destination $destPath -Force
    }
}

# Run single test file
function Test-SingleFile {
    param([string]$FileName)

    $testName = [System.IO.Path]::GetFileNameWithoutExtension($FileName)

    # Setup
    Initialize-Archive
    Move-AllTestsToArchive

    # Restore single test
    $restored = Restore-SingleTest -FileName $FileName
    if (-not $restored) {
        return $false
    }

    # Run test
    $success = Invoke-SingleTest -TestName $testName

    # Cleanup
    Cleanup-SingleTest -FileName $FileName

    return $success
}

# Run all tests in a category
function Test-Category {
    param([string]$CategoryName)

    Write-Host ""
    Write-Host "=======================================" -ForegroundColor Cyan
    Write-Host "  Testing Category: $CategoryName" -ForegroundColor Cyan
    Write-Host "=======================================" -ForegroundColor Cyan
    Write-Host ""

    $prefix = $CategoryPrefixes[$CategoryName]

    # Get all test files for this category from archive
    Initialize-Archive
    Move-AllTestsToArchive

    $categoryFiles = Get-ChildItem -Path $ArchiveDir -Filter "${prefix}*.cpp" -File

    if ($categoryFiles.Count -eq 0) {
        Write-WarningMsg "No test files found for category: $CategoryName"
        return $false
    }

    Write-Info "Found $($categoryFiles.Count) test files in category '$CategoryName'"
    Write-Host ""

    $results = @{}
    foreach ($file in $categoryFiles) {
        $results[$file.Name] = Test-SingleFile -FileName $file.Name
    }

    # Summary
    Write-Host ""
    Write-Host "---------------------------------------" -ForegroundColor Cyan
    Write-Host "Category Summary: $CategoryName" -ForegroundColor Cyan
    Write-Host "---------------------------------------" -ForegroundColor Cyan

    foreach ($file in $categoryFiles) {
        $status = if ($results[$file.Name]) { "[PASS]" } else { "[FAIL]" }
        $color = if ($results[$file.Name]) { "Green" } else { "Red" }
        Write-Host "  $($file.Name.PadRight(35)): $status" -ForegroundColor $color
    }

    $failedTests = ($results.GetEnumerator() | Where-Object { -not $_.Value }).Count
    if ($failedTests -gt 0) {
        Write-Host ""
        Write-ErrorMsg "$failedTests test(s) failed in category '$CategoryName'"
        return $false
    } else {
        Write-Host ""
        Write-Success "All tests passed in category '$CategoryName'"
        return $true
    }
}

# Main execution
try {
    Write-Host ""
    Write-Host "ESP32 Test Runner (One-File-At-A-Time)" -ForegroundColor Cyan
    Write-Host "=======================================" -ForegroundColor Cyan
    Write-Host ""

    # Clear previous log
    if (Test-Path $LogFile) {
        Clear-Content $LogFile
    }

    if ($TestFile) {
        # Single test file
        Write-Info "Running single test: $TestFile"
        $success = Test-SingleFile -FileName $TestFile

        if ($success) {
            Write-Host ""
            Write-Success "Test '$TestFile' completed successfully"
            exit 0
        } else {
            Write-Host ""
            Write-ErrorMsg "Test '$TestFile' failed"
            exit 1
        }
    }
    elseif ($Category -eq "all") {
        # All categories
        Write-Info "Running ALL test categories..."
        $allCategories = @("infra", "actuator", "sensor", "comm", "integration")
        $results = @{}

        foreach ($cat in $allCategories) {
            $results[$cat] = Test-Category -CategoryName $cat
        }

        # Final Summary
        Write-Host ""
        Write-Host "=======================================" -ForegroundColor Cyan
        Write-Host "         Final Summary" -ForegroundColor Cyan
        Write-Host "=======================================" -ForegroundColor Cyan
        Write-Host ""

        foreach ($cat in $allCategories) {
            $status = if ($results[$cat]) { "[PASS]" } else { "[FAIL]" }
            $color = if ($results[$cat]) { "Green" } else { "Red" }
            Write-Host "  $($cat.PadRight(15)): $status" -ForegroundColor $color
        }

        $failedCategories = ($results.GetEnumerator() | Where-Object { -not $_.Value }).Count
        if ($failedCategories -gt 0) {
            Write-Host ""
            Write-ErrorMsg "$failedCategories category(ies) failed"
            exit 1
        } else {
            Write-Host ""
            Write-Success "All categories passed!"
            exit 0
        }
    }
    else {
        # Single category
        $success = Test-Category -CategoryName $Category

        if ($success) {
            exit 0
        } else {
            exit 1
        }
    }
}
catch {
    Write-ErrorMsg "Script execution failed: $_"

    # Emergency cleanup
    Write-WarningMsg "Attempting emergency cleanup..."
    try {
        Move-AllTestsToArchive
    }
    catch {
        Write-ErrorMsg "Emergency cleanup failed - manual intervention required"
    }

    exit 1
}
