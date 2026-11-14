# Jarvis sur le PC : le serveur démarre avec Windows (sans fenêtre), et un raccourci
# « Jarvis » dans le menu Démarrer l'ouvre dans sa propre fenêtre, aussi avec Ctrl+Alt+J.
# Relancer ce script ne fait que réécrire les deux raccourcis. Pour défaire : supprimer
# « Jarvis serveur » dans shell:startup et « Jarvis » dans le menu Démarrer.

$dir = $PSScriptRoot
$pyw = (Get-Command pythonw -ErrorAction Stop).Source
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$shell = New-Object -ComObject WScript.Shell

$s = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Startup")) "Jarvis serveur.lnk"))
$s.TargetPath = $pyw
$s.Arguments = "`"$dir\server.py`""
$s.WorkingDirectory = $dir
$s.Save()

$a = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Programs")) "Jarvis.lnk"))
$a.TargetPath = $edge
$a.Arguments = "--app=http://127.0.0.1:7777"
$a.Hotkey = "CTRL+ALT+J"
$a.IconLocation = "$dir\docs\jarvis.ico"
$a.Save()

# Start it now too (does nothing if Jarvis already runs: the port is taken).
Start-Process $pyw -ArgumentList "`"$dir\server.py`"" -WorkingDirectory $dir
Write-Output "Jarvis installé : il démarre avec Windows. Ouvre-le avec Ctrl+Alt+J ou « Jarvis » dans le menu Démarrer."
