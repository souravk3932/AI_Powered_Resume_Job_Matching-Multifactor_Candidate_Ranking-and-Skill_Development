<#
.SYNOPSIS
  Starts the backend, the frontend and the AI service together in ONE window.
  Closing this window (or pressing Ctrl+C) stops all three, and everything they started.

.EXAMPLE
  .\start-all.ps1               # normal start (backend 5000, frontend 5173, AI service 8000)
  .\start-all.ps1 -Open         # also open the website in your browser when ready

.NOTES
  -BackendPort / -FrontendPort / -AiPort  change the ports (useful if one is busy)
  -AutoStopAfter <seconds>                stop by itself after that time (used for testing)
#>
param(
    [int]$BackendPort = 5000,
    [int]$FrontendPort = 5173,
    [int]$AiPort = 8000,
    [switch]$Open,
    [int]$AutoStopAfter = 0
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try { $Host.UI.RawUI.WindowTitle = "MINI - all services (close this window to stop them)" } catch {}

$PythonExe = Join-Path $Root "ai-service\.venv\Scripts\python.exe"

# ---------------------------------------------------------------------------
# 1. Pre-flight checks: stop early, with a clear message, instead of failing half-way
# ---------------------------------------------------------------------------
function Get-PortOwner([int]$Port) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { "unknown" }
    return "$name (PID $($conn.OwningProcess))"
}

$problems = @()
if (-not (Test-Path (Join-Path $Root "backend\node_modules")))  { $problems += "backend has no node_modules. Run:  cd backend ; npm install" }
if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) { $problems += "frontend has no node_modules. Run:  cd frontend ; npm install" }
if (-not (Test-Path $PythonExe))                                { $problems += "AI service virtual environment is missing ($PythonExe)" }
if (-not (Test-Path (Join-Path $Root "backend\.env")))          { $problems += "backend\.env is missing (copy backend\.env.example and fill it in)" }
if (-not (Test-Path (Join-Path $Root "ai-service\.env")))       { $problems += "ai-service\.env is missing (copy ai-service\.env.example and fill it in)" }

foreach ($item in @(@("Backend", $BackendPort), @("Frontend", $FrontendPort), @("AI service", $AiPort))) {
    $owner = Get-PortOwner $item[1]
    if ($owner) { $problems += "$($item[0]) port $($item[1]) is already used by $owner. Close that program (maybe an old terminal) or pick another port." }
}

if ($problems.Count -gt 0) {
    Write-Host ""
    Write-Host "Cannot start yet:" -ForegroundColor Red
    $problems | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    exit 1
}

# ---------------------------------------------------------------------------
# 2. A tiny helper (compiled once) that
#    a) puts THIS script in a Windows "job" that kills every process in it when the script ends
#       (Ctrl+C, closing the window, crash... anything), and
#    b) starts each service and prints its output with a [name] label.
# ---------------------------------------------------------------------------
if (-not ("ServiceRunner" -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class ServiceRunner
{
    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimits {
        public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit; public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize; public uint ActiveProcessLimit;
        public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimits {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit; public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attrs, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint size);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();

    static IntPtr job = IntPtr.Zero;
    static readonly object gate = new object();

    // Returns true when the "kill everything when I end" rule is active
    public static bool Init()
    {
        job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) return false;
        ExtendedLimits info = new ExtendedLimits();
        info.Basic.LimitFlags = 0x2000;  // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(typeof(ExtendedLimits));
        IntPtr ptr = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(info, ptr, false);
            if (!SetInformationJobObject(job, 9, ptr, (uint)size)) return false;  // 9 = extended limit information
        } finally { Marshal.FreeHGlobal(ptr); }
        // Put ourselves in the job FIRST, so every program we start later is automatically inside it too
        return AssignProcessToJobObject(job, GetCurrentProcess());
    }

    static void Print(string name, ConsoleColor color, string line)
    {
        lock (gate) {
            ConsoleColor old = Console.ForegroundColor;
            Console.ForegroundColor = color;
            Console.Write("[" + name + "] ");
            Console.ForegroundColor = old;
            Console.WriteLine(line);
        }
    }

    public static Process Run(string name, ConsoleColor color, string file, string args, string workDir, IDictionary env)
    {
        ProcessStartInfo psi = new ProcessStartInfo(file, args);
        psi.WorkingDirectory = workDir;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardInput = true;   // keeps your keystrokes out of the services
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding = Encoding.UTF8;
        foreach (DictionaryEntry e in env) { psi.EnvironmentVariables[Convert.ToString(e.Key)] = Convert.ToString(e.Value); }

        Process p = new Process();
        p.StartInfo = psi;
        DataReceivedEventHandler handler = delegate(object sender, DataReceivedEventArgs ev) {
            if (ev.Data != null) Print(name, color, ev.Data);
        };
        p.OutputDataReceived += handler;
        p.ErrorDataReceived += handler;
        p.Start();
        if (job != IntPtr.Zero) AssignProcessToJobObject(job, p.Handle);  // harmless if it is already inside
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        return p;
    }
}
'@
}

$jobActive = [ServiceRunner]::Init()
if (-not $jobActive) {
    Write-Host "Note: the automatic 'kill everything on exit' rule could not be enabled. Stop with Ctrl+C (not by closing the window)." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 3. Start the three services
# ---------------------------------------------------------------------------
$apiUrl = "http://localhost:$BackendPort"
$services = @(
    @{ Name = "ai-service"; Color = [ConsoleColor]::Magenta; File = $PythonExe
       Args = "-m uvicorn app.main:app --reload --port $AiPort"; Dir = Join-Path $Root "ai-service"
       Env  = @{ PYTHONUNBUFFERED = "1" } },
    @{ Name = "backend";    Color = [ConsoleColor]::Cyan;    File = "cmd.exe"
       Args = "/c npm run dev"; Dir = Join-Path $Root "backend"
       Env  = @{ PORT = "$BackendPort"; AI_SERVICE_URL = "http://localhost:$AiPort" } },
    @{ Name = "frontend";   Color = [ConsoleColor]::Green;   File = "cmd.exe"
       Args = "/c npm run dev -- --port $FrontendPort --strictPort"; Dir = Join-Path $Root "frontend"
       Env  = @{ VITE_API_URL = $apiUrl } }
)

Write-Host ""
Write-Host "Starting MINI ... (Ctrl+C or closing this window stops everything)" -ForegroundColor White

function Stop-All {
    foreach ($s in $services) {
        if ($s.Proc -and -not $s.Proc.HasExited) {
            # /T = also stop everything this program started (npm -> nodemon -> node ...)
            cmd.exe /c "taskkill /PID $($s.Proc.Id) /T /F >nul 2>&1" | Out-Null
        }
    }
}

try {
    foreach ($s in $services) {
        $s.Proc = [ServiceRunner]::Run($s.Name, $s.Color, $s.File, $s.Args, $s.Dir, $s.Env)
    }

    # -----------------------------------------------------------------------
    # 4. Wait until each service answers, then print a summary
    # -----------------------------------------------------------------------
    function Get-Json([string]$Url) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            return $r
        } catch { return $null }
    }

    $checks = @(
        # uvicorn listens on 127.0.0.1 (IPv4) only, so check that address, not "localhost"
        @{ Name = "AI service"; Url = "http://127.0.0.1:$AiPort/health";        Ready = $false },
        @{ Name = "Backend";    Url = "$apiUrl/api/health";                     Ready = $false },
        @{ Name = "Frontend";   Url = "http://localhost:$FrontendPort/";        Ready = $false }
    )
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline -and ($checks | Where-Object { -not $_.Ready })) {
        foreach ($c in $checks | Where-Object { -not $_.Ready }) {
            if (Get-Json $c.Url) { $c.Ready = $true }
        }
        if ($services | Where-Object { $_.Proc.HasExited }) { break }  # a service crashed: stop waiting
        Start-Sleep -Milliseconds 700
    }

    # The database connects a moment after the backend starts listening
    $dbState = "unknown"
    for ($i = 0; $i -lt 20; $i++) {
        $r = Get-Json "$apiUrl/api/health"
        if ($r) { $dbState = ($r.Content | ConvertFrom-Json).database; if ($dbState -eq "connected") { break } }
        Start-Sleep -Milliseconds 700
    }

    Write-Host ""
    Write-Host "==================== status ====================" -ForegroundColor White
    foreach ($c in $checks) {
        if ($c.Ready) { Write-Host ("  OK     {0,-11} {1}" -f $c.Name, $c.Url) -ForegroundColor Green }
        else          { Write-Host ("  FAILED {0,-11} did not answer in time (see its [label] lines above)" -f $c.Name) -ForegroundColor Red }
    }
    $dbColor = if ($dbState -eq "connected") { "Green" } else { "Yellow" }
    Write-Host ("  Database: {0}" -f $dbState) -ForegroundColor $dbColor
    Write-Host ""
    Write-Host "  Website:  http://localhost:$FrontendPort" -ForegroundColor White
    Write-Host "  Stop all: press Ctrl+C, or just close this window." -ForegroundColor White
    Write-Host "================================================" -ForegroundColor White
    Write-Host ""

    if ($Open -and ($checks | Where-Object { $_.Name -eq "Frontend" }).Ready) { Start-Process "http://localhost:$FrontendPort" }

    # -----------------------------------------------------------------------
    # 5. Keep running until Ctrl+C / window closed / every service has stopped
    # -----------------------------------------------------------------------
    $started = Get-Date
    while ($true) {
        Start-Sleep -Seconds 1
        foreach ($s in $services) {
            if ($s.Proc.HasExited -and -not $s.Reported) {
                $s.Reported = $true
                Write-Host ("[{0}] stopped (exit code {1})" -f $s.Name, $s.Proc.ExitCode) -ForegroundColor Yellow
            }
        }
        if (-not ($services | Where-Object { -not $_.Proc.HasExited })) { break }
        if ($AutoStopAfter -gt 0 -and ((Get-Date) - $started).TotalSeconds -ge $AutoStopAfter) {
            Write-Host "Auto-stop time reached." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping all services ..." -ForegroundColor Yellow
    Stop-All
    Write-Host "All services stopped." -ForegroundColor Green
}
