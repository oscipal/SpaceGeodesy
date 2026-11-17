# Run commands inside the pipeline container from Windows.
#   .\dc.ps1 build            build the image
#   .\dc.ps1 make all         run the chain
#   .\dc.ps1 make app         start the viewer on http://localhost:8501
#   .\dc.ps1 bash             interactive shell
# LiCSBAS works in the Docker volume "svartsengi-work" (mounted at /vol) because
# Windows bind mounts are slow for its many small files; results are copied back
# into this folder (results/, figures/qc/).
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Cmd)

$Image = "svartsengi-insar"
$Volume = "svartsengi-work"
$Root = $PSScriptRoot

if ($Cmd.Count -gt 0 -and $Cmd[0] -eq "build") {
    docker build -t $Image $Root
    exit $LASTEXITCODE
}
if ($Cmd.Count -eq 0) { $Cmd = @("make", "help") }

$tty = if ([Console]::IsInputRedirected) { "-i" } else { "-it" }
docker run --rm $tty -p 127.0.0.1:8501:8501 -v "${Root}:/work" -v "${Volume}:/vol" -e LICSBAS_WORK=/vol -w /work $Image @Cmd
exit $LASTEXITCODE
