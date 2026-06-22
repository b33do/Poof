#!/bin/bash

# Celestial Toolkit Desktop Launcher Wrapper Script
# Starts the privileged Python backend (running with root privileges via passwordless sudo)
# and opens the frontend UI inside Brave in standalone, borderless app mode.

PORT=8000
SCRIPT_DIR="/home/lani/Documents/Poof/kvm-build/scripts"
BACKEND_PATH="$SCRIPT_DIR/celestial_backend.py"

cleanup() {
    if [ -n "$BACKEND_PID" ]; then
        echo "[*] Stopping Celestial Toolkit backend (PID: $BACKEND_PID)..."
        sudo kill "$BACKEND_PID" 2>/dev/null
    fi
}

# Ensure standard signals clean up the backend server
trap cleanup EXIT INT TERM

# Check if the port is already in use
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "[*] Celestial backend is already running on port $PORT."
    # Find the existing backend pid if possible (so we can clean it up? Better not, just leave it be)
    BACKEND_PID=""
else
    echo "[*] Starting Celestial Toolkit backend..."
    # Run the backend script under sudo in the background
    sudo python3 "$BACKEND_PATH" > /tmp/celestial_backend.log 2>&1 &
    BACKEND_PID=$!
    
    # Wait for the backend to bind to the port
    echo "[*] Waiting for backend to start..."
    for i in {1..15}; do
        if lsof -i :$PORT >/dev/null 2>&1; then
            echo "[+] Backend started successfully."
            break
        fi
        sleep 0.5
    done
fi

# Launch Brave in app mode with a custom profile to prevent delegation to an existing session
echo "[*] Launching frontend in Brave App Mode..."
/usr/bin/brave --app="http://127.0.0.1:$PORT" --user-data-dir="/home/lani/.config/celestial-toolkit-profile" --no-first-run --no-default-browser-check

# The trap will clean up the backend process when Brave exits.

