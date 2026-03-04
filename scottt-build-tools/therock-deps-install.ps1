# List of packages to install
$packages = @(
    "astral-sh.uv",
    "Iterative.DVC"
    # for gfortran
    "StrawberryPerl.StrawberryPerl",
    "bloodrock.pkg-config-lite",
    # ninja 1.13.1+
    "Ninja-build.Ninja"
)

# Loop through each package and install
foreach ($pkg in $packages) {
    Write-Host "Installing $pkg..."
    winget install --id=$pkg --silent --accept-package-agreements --accept-source-agreements
}
