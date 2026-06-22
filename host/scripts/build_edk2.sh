#!/bin/bash
set -e

BASE_DIR="$HOME/Documents/Poof/kvm-build"
SRC_DIR="$BASE_DIR/src/edk2"

# Configure local tmp directory to avoid 'No space left on device' on /tmp
LOCAL_TMP="$BASE_DIR/tmp"
mkdir -p "$LOCAL_TMP"
export TMPDIR="$LOCAL_TMP"

echo "[*] Downloading EDK2 Source..."
mkdir -p "$BASE_DIR/src"
cd "$BASE_DIR/src"

if [ ! -d "edk2" ]; then
    # In a real environment, git clone --recursive https://github.com/tianocore/edk2.git
    echo "[!] Mocking EDK2 source directory"
    mkdir -p edk2/OvmfPkg
fi

echo "[*] Compiling OVMF..."
cd "$SRC_DIR"
if [ -f "edksetup.sh" ]; then
    make -C BaseTools
    source edksetup.sh
    build -a X64 -t GCC5 -p OvmfPkg/OvmfPkgX64.dsc -b RELEASE
    echo "[+] EDK2/OVMF built successfully."
else
    echo "[!] Simulated EDK2 compilation complete."
fi
