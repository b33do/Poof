# PowerShell script to clean up stale Virtual Machine PCI & USB registry entries on Windows guest
# Run as Administrator inside the VM.

# List of hypervisor PCI/USB Vendor IDs to clean up:
$badVendors = @("VEN_1B36", "VEN_1AF4", "VEN_1AB8", "VEN_5853", "VEN_80EE", "VEN_15AD", "VEN_0E0F", "VID_1B36", "VID_1AF4")

function Take-RegistryOwnership {
    param([string]$Path)
    try {
        $key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($Path, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::TakeOwnership)
        if ($key) {
            $acl = $key.GetAccessControl()
            $owner = [System.Security.Principal.NTAccount]"Administrators"
            $acl.SetOwner($owner)
            $key.SetAccessControl($acl)
            $key.Close()
            
            $key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($Path, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::ChangePermissions)
            $acl = $key.GetAccessControl()
            $rule = New-Object System.Security.AccessControl.RegistryAccessRule("Administrators", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
            $acl.SetAccessRule($rule)
            $key.SetAccessControl($acl)
            $key.Close()
        }
    } catch {}
}

function Remove-RegistryKeyRecurse {
    param(
        [string]$BasePath,
        [string]$SubKeyName
    )
    $fullPath = Join-Path $BasePath $SubKeyName
    $regFullPath = "SYSTEM\CurrentControlSet\Enum\$fullPath"
    
    Take-RegistryOwnership -Path $regFullPath
    try {
        $key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($regFullPath)
        if ($key) {
            $subKeys = $key.GetSubKeyNames()
            $key.Close()
            foreach ($sub in $subKeys) {
                Remove-RegistryKeyRecurse -BasePath (Join-Path $BasePath $SubKeyName) -SubKeyName $sub
            }
        }
    } catch {}
    
    Take-RegistryOwnership -Path $regFullPath
    try {
        $parentKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey("SYSTEM\CurrentControlSet\Enum\$BasePath", $true)
        if ($parentKey) {
            $parentKey.DeleteSubKeyTree($SubKeyName, $false)
            $parentKey.Close()
            Write-Host "[+] Successfully deleted registry key: HKLM:\SYSTEM\CurrentControlSet\Enum\$fullPath" -ForegroundColor Green
        }
    } catch {
        Write-Host "[-] Failed to delete registry key: HKLM:\SYSTEM\CurrentControlSet\Enum\$fullPath - $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Scan HKLM:\SYSTEM\CurrentControlSet\Enum\PCI
$pciPath = "SYSTEM\CurrentControlSet\Enum\PCI"
$pciKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($pciPath)
if ($pciKey) {
    $devices = $pciKey.GetSubKeyNames()
    $pciKey.Close()
    foreach ($dev in $devices) {
        foreach ($vendor in $badVendors) {
            if ($dev -like "*$vendor*") {
                Write-Host "[*] Found matching VM registry entry: PCI\$dev" -ForegroundColor Yellow
                Remove-RegistryKeyRecurse -BasePath "PCI" -SubKeyName $dev
            }
        }
    }
}

# Scan HKLM:\SYSTEM\CurrentControlSet\Enum\USB
$usbPath = "SYSTEM\CurrentControlSet\Enum\USB"
$usbKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($usbPath)
if ($usbKey) {
    $devices = $usbKey.GetSubKeyNames()
    $usbKey.Close()
    foreach ($dev in $devices) {
        foreach ($vendor in $badVendors) {
            if ($dev -like "*$vendor*") {
                Write-Host "[*] Found matching VM registry entry: USB\$dev" -ForegroundColor Yellow
                Remove-RegistryKeyRecurse -BasePath "USB" -SubKeyName $dev
            }
        }
    }
}

Write-Host "[*] Cleanup complete. Please restart the guest Windows system to apply changes." -ForegroundColor Cyan
# Pause so user can see output
Read-Host "Press Enter to exit"
