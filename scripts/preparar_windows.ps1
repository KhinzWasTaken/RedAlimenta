<#
.SYNOPSIS
  Deja un PC con Windows listo para probar RedAlimenta.

.DESCRIPTION
  Revisa los programas necesarios (y los instala con winget si se usa -Instalar), corrige los saltos de
  línea de los scripts que corren en contenedores, crea o completa infra\.env con claves aleatorias,
  busca puertos ocupados, crea el entorno de Python (.venv) y, con -Levantar, arranca todo en Docker.
  Se puede ejecutar varias veces: no borra datos ni cambia claves que ya existan.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\preparar_windows.ps1 -Instalar -Levantar
#>
param(
    [switch]$Instalar,     # instala con winget lo que falte
    [switch]$Levantar,     # al final construye y levanta el sistema completo en Docker
    [switch]$SinPython     # no crea .venv (solo hace falta para los scripts de prueba y Kubernetes)
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$faltan = @()

function Ok($m)    { Write-Host "  [ok] $m" -ForegroundColor Green }
function Aviso($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Paso($m)  { Write-Host "`n== $m" -ForegroundColor Cyan }
function Existe($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# ---------------------------------------------------------------------------------------------
Paso '1. Programas'
$programas = @(
    @{ Nombre = 'Git';            Comando = 'git';    Winget = 'Git.Git' },
    @{ Nombre = 'Docker Desktop'; Comando = 'docker'; Winget = 'Docker.DockerDesktop' },
    @{ Nombre = 'Python 3.12';    Comando = 'py';     Winget = 'Python.Python.3.12' },
    @{ Nombre = 'Node.js LTS';    Comando = 'node';   Winget = 'OpenJS.NodeJS.LTS' }
)
foreach ($p in $programas) {
    if (Existe $p.Comando) { Ok "$($p.Nombre)"; continue }
    if ($Instalar -and (Existe 'winget')) {
        Write-Host "  Instalando $($p.Nombre)..."
        winget install --id $p.Winget -e --accept-package-agreements --accept-source-agreements
        $faltan += "$($p.Nombre) (recién instalado: cierra y abre PowerShell)"
    } else {
        Aviso "Falta $($p.Nombre): winget install --id $($p.Winget) -e"
        $faltan += $p.Nombre
    }
}
if ($faltan.Count -gt 0) {
    Aviso 'Docker Desktop necesita WSL 2: si no lo tienes, en PowerShell como administrador: wsl --install (y reinicia).'
    Aviso 'Node.js solo hace falta para el modo de desarrollo (scripts\levantar.py); Docker no lo necesita.'
}

# ---------------------------------------------------------------------------------------------
Paso '2. Docker en marcha'
$dockerListo = $false
if (Existe 'docker') {
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { Ok 'Docker responde'; $dockerListo = $true }
    else { Aviso 'Docker no responde: abre Docker Desktop y espera a que diga "Engine running".' }
}

# ---------------------------------------------------------------------------------------------
Paso '3. Saltos de línea de los archivos que corren en contenedores'
$archivos = Get-ChildItem -Recurse -File -Include *.sh, Dockerfile, *.conf, *.template |
    Where-Object { $_.FullName -notmatch '\\(node_modules|\.venv|\.git)\\' }
$corregidos = 0
foreach ($f in $archivos) {
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    $texto = [Text.Encoding]::UTF8.GetString($bytes)
    if ($texto.Contains("`r`n")) {
        [IO.File]::WriteAllText($f.FullName, $texto.Replace("`r`n", "`n"), (New-Object Text.UTF8Encoding $false))
        $corregidos++
    }
}
if ($corregidos -gt 0) { Ok "$corregidos archivo(s) pasados de CRLF a LF" } else { Ok 'Todo en LF' }

# ---------------------------------------------------------------------------------------------
Paso '4. Puertos libres'
function Ocupado([int]$puerto) {
    [bool](Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue)
}
# Si los contenedores de RedAlimenta ya están arriba, sus puertos aparecen ocupados: no es un problema.
$propios = @()
if ($dockerListo) { $propios = @(docker ps --filter 'name=redalimenta' -q) }
$cambios = @{}
if ($propios.Count -eq 0) {
    foreach ($p in @(@{ Var = 'POSTGRES_PORT'; Puerto = 5432; Alterno = 5433; Que = 'PostgreSQL' },
                     @{ Var = 'GATEWAY_PORT';  Puerto = 8080; Alterno = 8081; Que = 'la aplicación' },
                     @{ Var = 'RABBITMQ_PORT'; Puerto = 5672; Alterno = 5673; Que = 'RabbitMQ' },
                     @{ Var = 'RABBITMQ_CONSOLA_PORT'; Puerto = 15672; Alterno = 15673; Que = 'consola de RabbitMQ' })) {
        if (Ocupado $p.Puerto) {
            Aviso "El puerto $($p.Puerto) ($($p.Que)) está ocupado; se usará $($p.Alterno)."
            $cambios[$p.Var] = "$($p.Alterno)"
        } else { Ok "Puerto $($p.Puerto) libre" }
    }
} else { Ok 'RedAlimenta ya está corriendo; se mantienen sus puertos' }

# ---------------------------------------------------------------------------------------------
Paso '5. infra\.env'
function Aleatorio([int]$n) {
    $bytes = New-Object byte[] $n
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    (([Convert]::ToBase64String($bytes)) -replace '[+/=]', '').Substring(0, $n)
}
$secretos = @{ POSTGRES_PASSWORD = 24; APP_DB_PASSWORD = 24; RABBITMQ_PASSWORD = 24; JWT_SECRETO = 48; TOKEN_INTERNO = 48 }
$rutaEnv = 'infra\.env'
$ejemplo = Get-Content 'infra\.env.example'
$nuevo = -not (Test-Path $rutaEnv)
$actual = if ($nuevo) { @() } else { @(Get-Content $rutaEnv) }

function Valor($lineas, $clave) {
    foreach ($l in $lineas) { if ($l -match "^\s*$clave=(.*)$") { return $Matches[1] } }
    return $null
}

$salida = New-Object System.Collections.Generic.List[string]
if ($nuevo) {
    foreach ($l in $ejemplo) {
        if ($l -match '^\s*([A-Z_]+)=(.*)$') {
            $k = $Matches[1]
            if ($secretos.ContainsKey($k)) { $l = "$k=$(Aleatorio $secretos[$k])" }
            elseif ($cambios.ContainsKey($k)) { $l = "$k=$($cambios[$k])" }
        }
        $salida.Add($l)
    }
    foreach ($k in $cambios.Keys) { if (-not (Valor $salida $k)) { $salida.Add("$k=$($cambios[$k])") } }
    Ok 'Creado con claves aleatorias'
} else {
    foreach ($l in $actual) {
        # JWT_SECRETO debe tener al menos 32 caracteres o los servicios no arrancan.
        if ($l -match '^\s*JWT_SECRETO=(.*)$' -and $Matches[1].Trim().Length -lt 32) {
            $l = "JWT_SECRETO=$(Aleatorio 48)"; Aviso 'JWT_SECRETO tenía menos de 32 caracteres: se generó uno nuevo'
        }
        # Un puerto que quedó en su valor por defecto y está ocupado pasa al alterno.
        if ($l -match '^\s*([A-Z_]+)=(\d+)\s*$' -and $cambios.ContainsKey($Matches[1]) -and
            [int]$Matches[2] -eq [int]$cambios[$Matches[1]] - 1) {
            $l = "$($Matches[1])=$($cambios[$Matches[1]])"; Ok "Cambiado $l"
        }
        $salida.Add($l)
    }
    foreach ($l in $ejemplo) {
        if ($l -notmatch '^\s*([A-Z_]+)=(.*)$') { continue }
        $k = $Matches[1]; $v = $Matches[2]
        if ($null -eq (Valor $salida $k)) {
            if ($secretos.ContainsKey($k)) { $v = Aleatorio $secretos[$k] }
            elseif ($cambios.ContainsKey($k)) { $v = $cambios[$k] }
            $salida.Add("$k=$v"); Ok "Agregada la clave que faltaba: $k"
        }
    }
    foreach ($k in $cambios.Keys) { if ($null -eq (Valor $salida $k)) { $salida.Add("$k=$($cambios[$k])") } }
    Ok 'Revisado'
}
[IO.File]::WriteAllLines((Join-Path $raiz $rutaEnv), $salida, (New-Object Text.UTF8Encoding $false))

# ---------------------------------------------------------------------------------------------
if (-not $SinPython) {
    Paso '6. Entorno de Python (.venv)'
    if (Existe 'py') {
        if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3 -m venv .venv }
        & .venv\Scripts\python.exe -m pip install -q --upgrade pip
        & .venv\Scripts\python.exe -m pip install -q -r requirements-dev.txt
        if ($LASTEXITCODE -eq 0) { Ok 'Dependencias instaladas en .venv' } else { Aviso 'pip falló; revisa el mensaje de arriba' }
    } else { Aviso 'Sin Python: se omite (Docker no lo necesita)' }
}

# ---------------------------------------------------------------------------------------------
$compose = 'docker compose -f infra/docker-compose.yml --env-file infra/.env --profile app'
$puerto = if ($cambios.ContainsKey('GATEWAY_PORT')) { $cambios['GATEWAY_PORT'] } else { (Valor $salida 'GATEWAY_PORT') }
if (-not $puerto) { $puerto = '8080' }

if ($Levantar) {
    Paso '7. Construir y levantar (la primera vez tarda varios minutos)'
    if (-not $dockerListo) { throw 'Docker no está en marcha: abre Docker Desktop y vuelve a ejecutar el script.' }
    Invoke-Expression "$compose up -d --build --wait"
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose falló. Revisa: $compose logs" }
    Ok "Listo. Abre http://localhost:$puerto (el tablero aparece cuando termina la carga del almacén, unos 30 s)"
}

Paso 'Siguiente paso'
if ($faltan.Count -gt 0) { Aviso "Pendiente: $($faltan -join ', '). Luego vuelve a ejecutar este script." }
if (-not $Levantar) { Write-Host "  Levantar:  $compose up -d --build --wait" }
Write-Host "  Abrir:     http://localhost:$puerto   (usuarios en docs\guion-demo.md, clave demo123)"
Write-Host "  Probar:    .venv\Scripts\python scripts\e2e.py --base http://localhost:$puerto"
Write-Host "  Apagar:    $compose down      (agrega -v para borrar los datos)"
