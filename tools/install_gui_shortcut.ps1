$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install the project environment before creating the shortcut.' }
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'OpenSTREAM GUI.lnk'
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '-m openstream.gui_launcher --output-root "' + (Join-Path $projectPath 'outputs\gui') + '"'
$shortcut.WorkingDirectory = $projectPath
$shortcut.Description = 'OpenSTREAM native Python models, inputs, calculations and plots'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Output $shortcutPath
