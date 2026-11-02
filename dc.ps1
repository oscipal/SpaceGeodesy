# Run commands inside the pipeline container from Windows.
#   .\dc.ps1 build            build the image
#   .\dc.ps1 make all         run the chain
#   .\dc.ps1 make app         start the viewer on http://localhost:8501
#   .\dc.ps1 bash             interactive shell
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Cmd)

$Image = "svartsengi-insar"
$Root = $PSScriptRoot

if ($Cmd.Count -gt 0 -and $Cmd[0] -eq "build") {
    docker build -t $Image $Root
    exit $LASTEXITCODE
}
if ($Cmd.Count -eq 0) { $Cmd = @("make", "help") }

docker run --rm -it -p 8501:8501 -v "${Root}:/work" -w /work $Image @Cmd
exit $LASTEXITCODE
