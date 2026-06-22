#!/usr/bin/env python3
import os
import sys

# Path to the NVIDIA GPU ROM in sysfs
ROM_PATH = "/sys/bus/pci/devices/0000:01:00.0/rom"
OUTPUT_DIR = "/var/lib/libvirt/roms"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "patched_gpu.rom")

def main():
    if os.getuid() != 0:
        print("[-] This script must be run as root (sudo).")
        sys.exit(1)

    print("[*] Enabling GPU ROM read...")
    try:
        with open(ROM_PATH, "r+b") as rom_enable:
            rom_enable.write(b"1")
    except Exception as e:
        print(f"[-] Failed to enable ROM: {e}")
        print("[!] Make sure the VM is SHUT DOWN before running this script.")
        sys.exit(1)

    print("[*] Reading GPU VBIOS...")
    try:
        with open(ROM_PATH, "rb") as rom_file:
            rom_data = rom_file.read()
    except Exception as e:
        print(f"[-] Failed to read ROM: {e}")
        # Disable ROM before exiting
        try:
            with open(ROM_PATH, "r+b") as rom_enable:
                rom_enable.write(b"0")
        except:
            pass
        sys.exit(1)

    # Disable ROM reading
    print("[*] Disabling GPU ROM read...")
    try:
        with open(ROM_PATH, "r+b") as rom_enable:
            rom_enable.write(b"0")
    except Exception as e:
        print(f"[-] Failed to disable ROM: {e}")

    if not rom_data:
        print("[-] Dumped ROM data is empty.")
        sys.exit(1)

    print(f"[*] Dumped ROM size: {len(rom_data)} bytes")

    # Patching: Find the first occurrence of 0x55 0xAA (BIOS Signature)
    # and strip everything before it.
    bios_sig = b"\x55\xaa"
    sig_offset = rom_data.find(bios_sig)
    if sig_offset == -1:
        print("[-] Failed to find BIOS signature (55 AA) in dumped ROM. Cannot patch.")
        sys.exit(1)

    print(f"[+] Found BIOS signature (55 AA) at offset: {sig_offset} bytes")
    patched_data = rom_data[sig_offset:]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"[*] Writing patched ROM to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "wb") as out_file:
        out_file.write(patched_data)

    # Set permissions so libvirt/qemu can read the ROM
    os.chmod(OUTPUT_DIR, 0o755)
    os.chmod(OUTPUT_FILE, 0o644)
    # Change ownership to qemu:qemu or libvirt-qemu:libvirt-qemu
    os.system(f"chown -R qemu:qemu {OUTPUT_DIR} 2>/dev/null || chown -R libvirt-qemu:libvirt-qemu {OUTPUT_DIR} 2>/dev/null || true")

    print("[+] GPU ROM successfully dumped, patched, and installed!")

if __name__ == "__main__":
    main()
