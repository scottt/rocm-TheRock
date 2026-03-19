#Requires -RunAsAdministrator

# Enable long path support (paths > 260 characters).
# See https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -Value 1
Write-Host "LongPathsEnabled set to 1. A reboot is required for this to take effect."

# Configure git to support long paths globally.
git config --global core.longpaths true
Write-Host "git core.longpaths set to true."

# Configure git to use symlinks globally.
git config --global core.symlinks true
Write-Host "git core.symlinks set to true."

# Enable Developer Mode (required for symlink creation without elevation).
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" /v AllowDevelopmentWithoutDevLicense /t REG_DWORD /d 1 /f
Write-Host "Developer Mode enabled."

# Install tools via winget.
# winget install --id Microsoft.VisualStudio.2022.BuildTools --source winget --override "--add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.VC.CMake.Project --add Microsoft.VisualStudio.Component.VC.ATL --add Microsoft.VisualStudio.Component.Windows11SDK.22621"
# winget install --id Git.Git -e --source winget --custom "/o:PathOption=CmdTools"
# winget install cmake -v 3.31.0
# winget install ninja-build.ninja ccache python strawberryperl bloodrock.pkg-config-lite
# winget install --id Iterative.DVC --silent --accept-source-agreements
# Write-Host "Tool installation complete."
