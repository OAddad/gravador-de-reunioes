# criar_atalho.ps1
# Cria o atalho "Gravador de Reuniões" (com ícone) na Área de Trabalho e no
# menu Iniciar. Ele abre o app direto, sem janela preta, e pode ser fixado
# na barra de tarefas (clique direito > Fixar na barra de tarefas).
# Autor: Addad
$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$shell = New-Object -ComObject WScript.Shell
$destinos = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('Programs')
)
foreach ($destino in $destinos) {
    $atalho = $shell.CreateShortcut((Join-Path $destino 'Gravador de Reuniões.lnk'))
    $atalho.TargetPath = Join-Path $pasta '.venv\Scripts\pythonw.exe'
    $atalho.Arguments = '"' + (Join-Path $pasta 'app.py') + '"'
    $atalho.WorkingDirectory = $pasta
    $atalho.IconLocation = (Join-Path $pasta 'icone.ico') + ',0'
    $atalho.Description = 'Grava e transcreve reuniões'
    $atalho.Save()
}
Write-Host 'Atalho "Gravador de Reuniões" criado na Área de Trabalho e no menu Iniciar.'
