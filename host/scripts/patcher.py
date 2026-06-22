#!/usr/bin/env python3
"""
Hardened KVM/QEMU Patcher
=========================
Applies all kernel-level and QEMU-level anti-detection patches as specified
in the hardened_kvm_master_prompt.md.

Usage:
    patcher.py kernel <linux-source-dir>
    patcher.py qemu   <qemu-source-dir>
"""
import os
import sys
import re


# ═══════════════════════════════════════════════════════════════════════
#  KERNEL PATCHES
# ═══════════════════════════════════════════════════════════════════════

def patch_kernel_cpuid_c(base_dir):
    """Strip hypervisor presence from CPUID leaves 0x1, 0x40000000-0x400000FF and mask Leaf 7 EDX."""
    path = os.path.join(base_dir, 'arch/x86/kvm/cpuid.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found")
        return
    with open(path, 'r') as f:
        content = f.read()

    # Part 1: Mask CPUID hypervisor bit and hypervisor leaves
    cpuid_patch = """\tu32 orig_eax = eax;
\tkvm_cpuid(vcpu, &eax, &ebx, &ecx, &edx, false);
\t/* --- Hardened KVM: Strip hypervisor presence --- */
\tif (orig_eax == 1) {
\t\tecx &= ~(1 << 31); /* Clear Hypervisor Present bit */
\t}
\tif (orig_eax >= 0x40000000 && orig_eax <= 0x400000FF) {
\t\teax = 0;
\t\tebx = 0;
\t\tecx = 0;
\t\tedx = 0;
\t}"""

    if 'orig_eax' not in content:
        content = content.replace(
            '\tkvm_cpuid(vcpu, &eax, &ebx, &ecx, &edx, false);',
            cpuid_patch
        )
        print("[+] Masked CPUID hypervisor bit and leaves in cpuid.c")

    # Part 2: Mask Leaf 7 EDX (prevent guest from scanning MSRs like ARCH_CAPABILITIES)
    # Search for Leaf 7 block: cpuid_entry_override(entry, CPUID_7_EDX);
    old_leaf7 = "cpuid_entry_override(entry, CPUID_7_EDX);"
    new_leaf7 = "cpuid_entry_override(entry, CPUID_7_EDX);\n\t\tentry->edx &= 0x73FFFFFF; /* Mask security/capabilities bits */"
    if new_leaf7 not in content and old_leaf7 in content:
        content = content.replace(old_leaf7, new_leaf7)
        print("[+] Masked CPUID Leaf 7 EDX first override")

    old_leaf7_1 = "cpuid_entry_override(entry, CPUID_7_1_EDX);\n\t\t\tentry->ebx = 0;\n\t\t\tentry->ecx = 0;"
    new_leaf7_1 = "cpuid_entry_override(entry, CPUID_7_1_EDX);\n\t\t\tentry->ebx = 0;\n\t\t\tentry->ecx = 0;\n\t\t\tentry->edx &= 0x73FFFFFF;"
    if new_leaf7_1 not in content and old_leaf7_1 in content:
        content = content.replace(old_leaf7_1, new_leaf7_1)
        print("[+] Masked CPUID Leaf 7.1 EDX second override")

    old_leaf7_2 = "cpuid_entry_override(entry, CPUID_7_2_EDX);\n\t\t\tentry->ecx = 0;\n\t\t\tentry->ebx = 0;\n\t\t\tentry->eax = 0;"
    new_leaf7_2 = "cpuid_entry_override(entry, CPUID_7_2_EDX);\n\t\t\tentry->ecx = 0;\n\t\t\tentry->ebx = 0;\n\t\t\tentry->eax = 0;\n\t\t\tedx &= 0x73FFFFFF;"
    # Check if there is an error in patch where entry->edx was referred to as edx
    if "entry->edx &= 0x73FFFFFF;" not in content:
        # We will use the correct safe assignment: entry->edx &= 0x73FFFFFF;
        new_leaf7_2 = "cpuid_entry_override(entry, CPUID_7_2_EDX);\n\t\t\tentry->ecx = 0;\n\t\t\tentry->ebx = 0;\n\t\t\tentry->eax = 0;\n\t\t\tentry->edx &= 0x73FFFFFF;"
        if old_leaf7_2 in content:
            content = content.replace(old_leaf7_2, new_leaf7_2)
            print("[+] Masked CPUID Leaf 7.2 EDX third override")

    with open(path, 'w') as f:
        f.write(content)
    print("[+] Patched arch/x86/kvm/cpuid.c complete")


# ─── AMD SVM ──────────────────────────────────────────────────────────

def patch_kernel_svm_h(base_dir):
    """Add TSC tracking fields to struct vcpu_svm."""
    # NIKA registers fields in include/linux/kvm_host.h instead of svm.h
    pass


def patch_kernel_svm_c(base_dir):
    """Inject dynamic TSC scaling CPUID exit handler and disable RDTSC/RDTSCP/UD intercepts in svm.c."""
    path = os.path.join(base_dir, 'arch/x86/kvm/svm/svm.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found")
        return
    with open(path, 'r') as f:
        content = f.read()

    # Part 1: Clear RDTSC/RDTSCP and UD_VECTOR intercepts in init_vmcb
    # Clear UD_VECTOR exception intercept
    content = content.replace(
        '\tset_exception_intercept(svm, UD_VECTOR);',
        '\t// set_exception_intercept(svm, UD_VECTOR); /* Clear UD intercept for stealth */\n\tclr_exception_intercept(svm, UD_VECTOR);'
    )
    
    # Clear RDTSC/RDTSCP intercepts
    content = content.replace(
        '\tsvm_set_intercept(svm, INTERCEPT_RDTSC);',
        '\tsvm_clr_intercept(svm, INTERCEPT_RDTSC);'
    )
    content = content.replace(
        '\tsvm_set_intercept(svm, INTERCEPT_RDTSCP);',
        '\tsvm_clr_intercept(svm, INTERCEPT_RDTSCP);'
    )

    # In svm_recalc_instruction_intercepts, clear intercepts
    old_recalc = """\tsvm_set_intercept(svm, INTERCEPT_RDTSCP);
\tsvm_set_intercept(svm, INTERCEPT_RDTSC);"""
    new_recalc = """\tsvm_clr_intercept(svm, INTERCEPT_RDTSCP);
\tsvm_clr_intercept(svm, INTERCEPT_RDTSC);"""
    content = content.replace(old_recalc, new_recalc)

    # Part 2: Inject dynamic hardware-level TSC scaling cpuid_interception function
    handlers_code = """/* ── Hardened KVM: Dynamic Hardware TSC Scaling cpuid_interception ── */
static int cpuid_interception(struct kvm_vcpu *vcpu)
{
	vcpu->total_exit_time += 2100; /* Adjust for exit timing penalty */
	u64 tsc = rdtsc();
	u64 ratio = mul_u64_u64_div_u64(1ULL << kvm_caps.tsc_scaling_ratio_frac_bits, tsc - vcpu->total_exit_time, tsc);
	if (ratio > 1ULL << (kvm_caps.tsc_scaling_ratio_frac_bits - 2) && ratio < 1ULL << kvm_caps.tsc_scaling_ratio_frac_bits) {
		kvm_caps.default_tsc_scaling_ratio = ratio;
		vcpu->arch.tsc_scaling_ratio = ratio;
		wrmsrq(MSR_AMD64_TSC_RATIO, ratio);
		__this_cpu_write(current_tsc_ratio, ratio);
	}
	return kvm_emulate_cpuid(vcpu);
}

"""
    if 'cpuid_interception' not in content:
        content = content.replace(
            'static int (*const svm_exit_handlers[])(struct kvm_vcpu *vcpu) = {',
            handlers_code + 'static int (*const svm_exit_handlers[])(struct kvm_vcpu *vcpu) = {'
        )
        print("[+] Injected cpuid_interception dynamic scaling function into svm.c")

    # Part 3: Register CPUID exit handler in svm_exit_handlers table
    content = content.replace(
        '\t[SVM_EXIT_CPUID]\t\t\t= kvm_emulate_cpuid,',
        '\t[SVM_EXIT_CPUID]\t\t\t= cpuid_interception,'
    )
    print("[+] Registered cpuid_interception in svm_exit_handlers table")

    # Restore default handlers for RDTSC/RDTSCP (avoid patching them since they are not intercepted)
    content = re.sub(
        r'\[SVM_EXIT_RDTSCP\]\s*=\s*handle_rdtscp,',
        '[SVM_EXIT_RDTSCP]\t\t\t= kvm_handle_invalid_op,',
        content
    )
    content = re.sub(
        r'\[SVM_EXIT_RDTSC\]\s*=\s*handle_rdtsc,',
        '',
        content
    )

    with open(path, 'w') as f:
        f.write(content)
    print("[+] Patched arch/x86/kvm/svm/svm.c — AMD dynamic TSC scaling complete")


# ─── Intel VMX ────────────────────────────────────────────────────────

def patch_kernel_vmx_h(base_dir):
    """Add TSC tracking fields to struct vcpu_vmx."""
    path = os.path.join(base_dir, 'arch/x86/kvm/vmx/vmx.h')
    # Register fields in include/linux/kvm_host.h instead of vmx.h
    pass


def patch_kernel_vmx_c(base_dir):
    """Inject handle_cpuid dynamic scaling exit handler and disable RDTSC/RDTSCP intercepts in vmx.c."""
    path = os.path.join(base_dir, 'arch/x86/kvm/vmx/vmx.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found — skipping VMX code patch")
        return
    with open(path, 'r') as f:
        content = f.read()

    # Part 1: Inject dynamic hardware-level TSC scaling handle_cpuid function
    handlers_code = """/* ── Hardened KVM: Dynamic Hardware TSC Scaling handle_cpuid ── */
static int handle_cpuid(struct kvm_vcpu *vcpu)
{
	vcpu->total_exit_time += 2100; /* Adjust for exit timing penalty */
	u64 tsc = rdtsc();
	u64 ratio = mul_u64_u64_div_u64(1ULL << kvm_caps.tsc_scaling_ratio_frac_bits, tsc - vcpu->total_exit_time, tsc);
	if (ratio > 1ULL << (kvm_caps.tsc_scaling_ratio_frac_bits - 2) && ratio < 1ULL << kvm_caps.tsc_scaling_ratio_frac_bits) {
		kvm_caps.default_tsc_scaling_ratio = ratio;
		vcpu->arch.tsc_scaling_ratio = ratio;
		vmcs_write64(TSC_MULTIPLIER, ratio);
	}
	return kvm_emulate_cpuid(vcpu);
}

"""
    if 'handle_cpuid' not in content:
        # Find the VMX exit handlers table and inject before it
        table_marker = 'static int (*kvm_vmx_exit_handlers[])'
        if table_marker not in content:
            table_marker = 'static int (*const kvm_vmx_exit_handlers[])'
        if table_marker in content:
            content = content.replace(table_marker, handlers_code + table_marker)
            print("[+] Injected handle_cpuid dynamic scaling function into vmx.c")
        else:
            content += '\n' + handlers_code
            print("[+] Appended handle_cpuid dynamic scaling function to vmx.c (fallback)")

    # Part 2: Disable RDTSC exiting in vmx_exec_control (clear the bit instead of setting it)
    exec_ctrl_pattern = 'exec_control &= ~(CPU_BASED_RDTSC_EXITING |'
    exec_ctrl_patch = (
        '/* Hardened KVM: Disable RDTSC/RDTSCP intercepts for timing evasion */\n'
        '\texec_control &= ~(\n'
        '\t\tCPU_BASED_RDTSC_EXITING |'
    )
    if exec_ctrl_pattern in content:
        content = content.replace(exec_ctrl_pattern, exec_ctrl_patch)
        print("[+] Disabled RDTSC exiting in vmx_exec_control")

    # Part 3: Register handlers in the exit table using regular expressions
    content = re.sub(
        r'\[EXIT_REASON_CPUID\]\s*=\s*kvm_emulate_cpuid,',
        '[EXIT_REASON_CPUID]                   = handle_cpuid,',
        content
    )
    content = re.sub(
        r'\[EXIT_REASON_VMCALL\]\s*=\s*kvm_emulate_hypercall,',
        '[EXIT_REASON_VMCALL]                  = kvm_handle_invalid_op,',
        content
    )
    print("[+] Registered CPUID scaling handler in VMX exit handlers table")

    # Revert any previously injected RDTSC exits
    content = re.sub(
        r'\[EXIT_REASON_RDTSC\]\s*=\s*handle_rdtsc,',
        '',
        content
    )
    content = re.sub(
        r'\[EXIT_REASON_RDTSCP\]\s*=\s*handle_rdtscp,',
        '',
        content
    )

    with open(path, 'w') as f:
        f.write(content)
    print("[+] Patched arch/x86/kvm/vmx/vmx.c — Intel timing evasion complete")


# ─── MSR Hiding ───────────────────────────────────────────────────────

def patch_kernel_x86_c(base_dir):
    """Hide KVM synthetic MSRs by injecting #GP faults and append timing fields to kvm_host.h."""
    # 1. Patch x86.c (MSR hiding)
    path_x86 = os.path.join(base_dir, 'arch/x86/kvm/x86.c')
    if os.path.exists(path_x86):
        with open(path_x86, 'r') as f:
            content_x86 = f.read()

        marker = '/* Hardened KVM: MSR hiding */'
        if marker not in content_x86:
            msr_patch = """
\t/* Hardened KVM: MSR hiding */
\t/* Inject #GP for any access to KVM synthetic MSR range */
\tif (msr_info->index >= 0x4b564d00 && msr_info->index <= 0x4b564dff) {
\t\treturn 1; /* #GP fault */
\t}
"""
            func_sig = 'int kvm_get_msr_common(struct kvm_vcpu *vcpu, struct msr_data *msr_info)\n{'
            if func_sig in content_x86:
                content_x86 = content_x86.replace(func_sig, func_sig + msr_patch)
                with open(path_x86, 'w') as f:
                    f.write(content_x86)
                print("[+] Patched arch/x86/kvm/x86.c — KVM MSR range hidden with #GP")
            else:
                print("[-] Warning: kvm_get_msr_common signature not found in x86.c")
        else:
            print("[*] arch/x86/kvm/x86.c MSR hiding already patched")

    # 2. Patch include/linux/kvm_host.h (struct kvm_vcpu variables)
    path_host = os.path.join(base_dir, 'include/linux/kvm_host.h')
    if os.path.exists(path_host):
        with open(path_host, 'r') as f:
            content_host = f.read()

        if 'last_exit_start' not in content_host:
            # We will insert the timing variables right before struct kvm_vcpu's mmio_needed variable or valid_wakeup
            # struct kvm_vcpu has:
            # \tunsigned int halt_poll_ns;
            # \tbool valid_wakeup;
            old_host = "\tunsigned int halt_poll_ns;\n\tbool valid_wakeup;"
            new_host = "\tunsigned int halt_poll_ns;\n\tbool valid_wakeup;\n\n\t/* Hardened KVM: exit timing tracking variables */\n\tu64 last_exit_start;\n\tu64 total_exit_time;"
            if old_host in content_host:
                content_host = content_host.replace(old_host, new_host)
                with open(path_host, 'w') as f:
                    f.write(content_host)
                print("[+] Patched include/linux/kvm_host.h — added last_exit_start and total_exit_time")
            else:
                print("[-] Warning: Struct kvm_vcpu pattern not found in kvm_host.h")
        else:
            print("[*] include/linux/kvm_host.h already patched")


# ═══════════════════════════════════════════════════════════════════════
#  QEMU PATCHES
# ═══════════════════════════════════════════════════════════════════════

def patch_qemu_smbios(base_dir):
    """Replace QEMU/Bochs strings in SMBIOS tables."""
    path = os.path.join(base_dir, 'hw/smbios/smbios.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found")
        return
    with open(path, 'r') as f:
        content = f.read()

    replacements = {
        '"QEMU"': '"ASUSTeK COMPUTER INC."',
        '"Bochs"': '"ASUSTeK COMPUTER INC."',
        '"BOCHS "': '"ASUS  "',
        '"BXPC"': '"ROGMAXIM"',
        '"BXPC    "': '"ROGMAXIM"',
        '"FOCP"': '"FACP"',
    }
    patched = False
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            patched = True

    if patched:
        with open(path, 'w') as f:
            f.write(content)
        print("[+] Patched hw/smbios/smbios.c — SMBIOS strings sanitized")
    else:
        print("[*] hw/smbios/smbios.c already patched or no matching strings")


def patch_qemu_nvme(base_dir):
    """Spoof NVMe controller serial/model to Samsung SSD 990 PRO."""
    path = os.path.join(base_dir, 'hw/block/nvme.c')
    if not os.path.exists(path):
        # Try alternate path
        path = os.path.join(base_dir, 'hw/nvme/ctrl.c')
    if not os.path.exists(path):
        print(f"[-] NVMe source not found — skipping")
        return
    with open(path, 'r') as f:
        content = f.read()

    marker = '/* Hardened KVM: NVMe spoofing */'
    if marker in content:
        print("[*] NVMe controller already patched")
        return

    # Find the identity setup and inject overrides after it
    nvme_patch = """
    /* Hardened KVM: NVMe spoofing */
    pstrcpy((char *)id->mn, sizeof(id->mn), "Samsung SSD 990 PRO 2TB");
    pstrcpy((char *)id->sn, sizeof(id->sn), "S73KNS0W408912Y");
    pstrcpy((char *)id->fr, sizeof(id->fr), "EL1O6B0Q");
"""
    # Look for where id_ctrl fields are populated
    patterns = [
        'id->vid = cpu_to_le16',
        'id_ctrl->vid = cpu_to_le16',
        'n->id_ctrl.vid',
    ]
    injected = False
    for pat in patterns:
        if pat in content:
            # Find the line and inject after it
            idx = content.index(pat)
            # Find end of statement
            end = content.index(';', idx) + 1
            content = content[:end] + nvme_patch + content[end:]
            injected = True
            break

    if injected:
        with open(path, 'w') as f:
            f.write(content)
        print(f"[+] Patched {os.path.relpath(path, base_dir)} — NVMe identity spoofed")
    else:
        print(f"[-] Warning: Could not find NVMe identity init pattern in {path}")


def patch_qemu_ide(base_dir):
    """Replace 'QEMU HARDDISK' and 'QEMU DVD-ROM' in IDE identify data."""
    path = os.path.join(base_dir, 'hw/ide/core.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found — skipping IDE patch")
        return
    with open(path, 'r') as f:
        content = f.read()

    replacements = {
        '"QEMU HARDDISK"': '"WDC WD10EZEX-08WN4A0"',
        '"QEMU DVD-ROM"': '"HL-DT-ST DVDRAM GH24NSB0"',
        '"QEMU CD-ROM"': '"HL-DT-ST DVDRAM GH24NSB0"',
        '"QEMU MICRODRIVE"': '"TOSHIBA MK3276GSX"',
        '"QM00001"': '"WD-WCC6Y1HT8KL2"',  # Default serial
        '"QM00002"': '"WD-WCC6Y2RK4P91"',
        '"QM00003"': '"WD-WCC6Y3XT7N83"',
    }
    patched = False
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            patched = True

    if patched:
        with open(path, 'w') as f:
            f.write(content)
        print("[+] Patched hw/ide/core.c — IDE device strings spoofed")
    else:
        print("[*] hw/ide/core.c already patched or no matching strings")


def patch_qemu_scsi(base_dir):
    """Sanitize SCSI INQUIRY return data."""
    path = os.path.join(base_dir, 'hw/scsi/scsi-disk.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found — skipping SCSI patch")
        return
    with open(path, 'r') as f:
        content = f.read()

    replacements = {
        '"QEMU"': '"SAMSUNG"',
        '"QEMU HARDDISK"': '"SSD 990 PRO 2TB"',
        '"QEMU CD-ROM"': '"BD-RE BH16NS55"',
        '"QEMU    "': '"SAMSUNG "',
        '"QEMU HARDDISK   "': '"SSD 990 PRO 2TB "',
    }
    patched = False
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            patched = True

    if patched:
        with open(path, 'w') as f:
            f.write(content)
        print("[+] Patched hw/scsi/scsi-disk.c — SCSI INQUIRY sanitized")
    else:
        print("[*] hw/scsi/scsi-disk.c already patched or no matching strings")


def patch_qemu_pci_ids(base_dir):
    """Replace Red Hat PCI Vendor ID (0x1b36) and Bochs (0x1234) with CPU-specific IDs (0x1022 for AMD, 0x8086 for Intel)."""
    # Detect CPU vendor
    target_vid = "8086"
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "vendor_id" in line:
                    if "AuthenticAMD" in line:
                        target_vid = "1022"
                    break
    except:
        pass
    print(f"[*] CPU vendor check: using Vendor ID 0x{target_vid}")

    # Root Port Device ID alignment based on CPU vendor: 1453 for AMD, 1901 for Intel
    target_rp_did = "1453" if target_vid == "1022" else "1901"
    print(f"[*] Aligned PCIe Root Port Device ID: 0x{target_rp_did}")

    # Read device ID from vars.sh
    device_id = "2910"
    try:
        with open("/home/lani/Documents/Poof/Nika-Read-Only-main/vars.sh", "r") as f:
            for line in f:
                if line.startswith("device="):
                    device_id = line.split("=")[1].strip().strip('"').strip("'")
    except Exception as e:
        print(f"[-] Could not read vars.sh for device ID, using default {device_id}: {e}")
    print(f"[*] Bochs VGA Device ID to use: 0x{device_id}")

    # 1. Patch include/hw/pci/pci.h
    pci_h_path = os.path.join(base_dir, 'include/hw/pci/pci.h')
    if os.path.exists(pci_h_path):
        with open(pci_h_path, 'r') as f:
            content = f.read()
        
        # Replace PCI_VENDOR_ID_QEMU
        content = re.sub(r'#define\s+PCI_VENDOR_ID_QEMU\s+0x[0-9a-fA-F]+', f'#define PCI_VENDOR_ID_QEMU               0x{target_vid}', content)
        # Replace PCI_VENDOR_ID_REDHAT (Align with host CPU vendor for consistency)
        content = re.sub(r'#define\s+PCI_VENDOR_ID_REDHAT\s+0x[0-9a-fA-F]+', f'#define PCI_VENDOR_ID_REDHAT             0x{target_vid}', content)
        # Replace PCI_DEVICE_ID_QEMU_VGA
        content = re.sub(r'#define\s+PCI_DEVICE_ID_QEMU_VGA\s+0x[0-9a-fA-F]+', f'#define PCI_DEVICE_ID_QEMU_VGA           0x{device_id}', content)
        # Replace PCI_DEVICE_ID_REDHAT_PCIE_RP (Align with host CPU: 0x1453 AMD PCIe Root Port or 0x1901 Intel Skylake Root Port)
        content = re.sub(r'#define\s+PCI_DEVICE_ID_REDHAT_PCIE_RP\s+0x[0-9a-fA-F]+', f'#define PCI_DEVICE_ID_REDHAT_PCIE_RP     0x{target_rp_did}', content)
        
        with open(pci_h_path, 'w') as f:
            f.write(content)
        print("[+] Patched include/hw/pci/pci.h")

    # 2. Patch hw/display/qxl.c
    qxl_c_path = os.path.join(base_dir, 'hw/display/qxl.c')
    if os.path.exists(qxl_c_path):
        with open(qxl_c_path, 'r') as f:
            content = f.read()
        if 'k->vendor_id = REDHAT_PCI_VENDOR_ID;' in content:
            content = content.replace(
                'k->vendor_id = REDHAT_PCI_VENDOR_ID;',
                f'k->vendor_id = 0x{target_vid};'
            )
            with open(qxl_c_path, 'w') as f:
                f.write(content)
            print("[+] Patched hw/display/qxl.c vendor_id override")

    # Target: the xhci (USB 3.0 controller) which uses Red Hat vendor ID
    targets = [
        ('hw/usb/hcd-xhci.c', '0x1b36', f'0x{target_vid}', '0x000d', '0xa12f'),
        ('hw/usb/hcd-xhci-pci.c', '0x1b36', f'0x{target_vid}', '0x000d', '0xa12f'),
        ('hw/usb/hcd-xhci-pci.c', 'PCI_VENDOR_ID_REDHAT', f'0x{target_vid}', 'PCI_DEVICE_ID_REDHAT_XHCI', '0xa12f'),
    ]
    for rel_path, old_vid, new_vid, old_did, new_did in targets:
        path = os.path.join(base_dir, rel_path)
        if not os.path.exists(path):
            continue
        with open(path, 'r') as f:
            content = f.read()
        modified = False
        if old_vid in content:
            content = content.replace(old_vid, new_vid)
            modified = True
        if old_did in content:
            content = content.replace(old_did, new_did)
            modified = True
        if modified:
            with open(path, 'w') as f:
                f.write(content)
            print(f"[+] Patched {rel_path} — PCI VID/DID sanitized")

    # Patch Q35 MCH device ID to match EDK2 firmware expectation
    # Without this, OVMF hangs at PCI init because it can't find the MCH
    edk2bridge_key = f"edk2bridge_{target_vid}="
    edk2bridge = "160f" if target_vid == "1022" else "1901"
    try:
        with open("/home/lani/Documents/Poof/Nika-Read-Only-main/vars.sh", "r") as f:
            for line in f:
                if line.startswith(edk2bridge_key):
                    edk2bridge = line.split("=")[1].strip().strip('"').strip("'")
    except Exception as e:
        print(f"[-] Could not read vars.sh for {edk2bridge_key}, using default {edk2bridge}: {e}")
    print(f"[*] Q35 MCH bridge device ID to use: 0x{edk2bridge}")

    pci_ids_path = os.path.join(base_dir, 'include/hw/pci/pci_ids.h')
    if os.path.exists(pci_ids_path):
        with open(pci_ids_path, 'r') as f:
            content = f.read()
        m = re.search(r'#define\s+PCI_DEVICE_ID_INTEL_P35_MCH\s+0x[0-9a-fA-F]+', content)
        if m:
            old_define = m.group(0)
            new_define = f'#define PCI_DEVICE_ID_INTEL_P35_MCH      0x{edk2bridge}'
            if old_define != new_define:
                content = content.replace(old_define, new_define)
                with open(pci_ids_path, 'w') as f:
                    f.write(content)
                print(f"[+] Patched include/hw/pci/pci_ids.h — Q35 MCH device ID: {old_define.split()[-1]} → 0x{edk2bridge}")
            else:
                print(f"[*] include/hw/pci/pci_ids.h — Q35 MCH already patched to 0x{edk2bridge}")
        else:
            print(f"[-] Warning: Q35 MCH define not found in pci_ids.h")

    # Patch the generic i440fx/q35 PCI host bridge identifiers
    for rel_path in ['hw/pci-host/q35.c', 'hw/pci-host/i440fx.c']:
        path = os.path.join(base_dir, rel_path)
        if not os.path.exists(path):
            continue
        with open(path, 'r') as f:
            content = f.read()
        
        modified = False
        # These typically already use Intel IDs, but verify no QEMU strings leak
        if '"QEMU"' in content or '"Red Hat"' in content:
            content = content.replace('"QEMU"', '"Intel"')
            content = content.replace('"Red Hat"', '"Intel"')
            modified = True
            
        if rel_path == 'hw/pci-host/q35.c' and 'k->vendor_id = PCI_VENDOR_ID_INTEL;' in content:
            content = content.replace('k->vendor_id = PCI_VENDOR_ID_INTEL;', f'k->vendor_id = 0x{target_vid};')
            modified = True
            print(f"[+] Patched q35.c host bridge vendor_id to 0x{target_vid}")
            
        if modified:
            with open(path, 'w') as f:
                f.write(content)
            print(f"[+] Patched {rel_path} complete")


def patch_qemu_acpi(base_dir):
    """Sanitize ACPI table OEM IDs and remove WAET table."""
    # Patch ACPI OEM strings across all table generators
    acpi_files = [
        'hw/acpi/aml-build.c',
        'hw/i386/acpi-build.c',
        'hw/arm/virt-acpi-build.c',
        'include/hw/acpi/aml-build.h',
        'roms/seabios/src/config.h',
        'roms/seabios/src/fw/q35-acpi-dsdt.dsl',
        'roms/seabios/src/fw/ssdt-proc.dsl',
        'roms/seabios/src/fw/ssdt-pcihp.dsl',
        'roms/seabios/src/fw/ssdt-misc.dsl',
        'roms/seabios-hppa/src/config.h',
        'roms/seabios-hppa/src/fw/q35-acpi-dsdt.dsl',
        'roms/seabios-hppa/src/fw/ssdt-proc.dsl',
        'roms/seabios-hppa/src/fw/ssdt-pcihp.dsl',
        'roms/seabios-hppa/src/fw/ssdt-misc.dsl',
        'hw/i386/fw_cfg.c',
        'hw/misc/pvpanic-isa.c',
        'hw/acpi/vmgenid.c',
        'include/standard-headers/linux/qemu_fw_cfg.h',
        'hw/riscv/virt-acpi-build.c',
        'hw/arm/virt-acpi-build.c',
        'roms/seabios/src/fw/acpi.c',
        'roms/seabios-hppa/src/fw/acpi.c',
    ]
    for rel_path in acpi_files:
        path = os.path.join(base_dir, rel_path)
        if not os.path.exists(path):
            continue
        with open(path, 'r') as f:
            content = f.read()

        replacements = {
            '"BOCHS "': '"ASUS  "',
            '"BXPC"': '"ROGMAXIM"',
            '"BXPC    "': '"ROGMAXIM"',
            '"BXPCSSDT"': '"AMDTSSDT"',
            '"BXDSDT"': '"AMDTDSDT"',
            '"BXSSDP"': '"AMDTAMDP"',
            '"BXHPET"': '"AMI HPET"',
            '"BXFACP"': '"AMI FACP"',
            '"BXMADT"': '"AMI MADT"',
            '"BXWAET"': '"DELETED"',
            '"QEMU0002"': '"PNP0C02"',
            '"QEMU0001"': '"PNP0C02"',
            '"QEMUVGID"': '"PNP0C02"',
            '"FWCF"': '"FWBD"',
            '"PEVT"': '"ERR0"',
            '"VGEN"': '"VGID"',
            '"\\\\_SB.VGEN"': '"\\\\_SB.VGID"',
        }
        patched = False
        for old, new in replacements.items():
            if old in content:
                content = content.replace(old, new)
                patched = True

        if rel_path == 'hw/acpi/aml-build.c':
            fadt_qemu = 'build_append_padded_str(tbl, "QEMU", 8, \'\\0\');'
            fadt_clean = 'build_append_padded_str(tbl, "", 8, \'\\0\');'
            if fadt_qemu in content:
                content = content.replace(fadt_qemu, fadt_clean)
                patched = True
                print("[+] Patched aml-build.c — FADT Hypervisor Vendor Identity stripped")

        if rel_path == 'hw/i386/acpi-build.c':
            # 1. Comment out build_waet if it isn't already
            if '/* Hardened VM: build_waet' not in content and 'build_waet(tables_blob' in content:
                content = content.replace(
                    'build_waet(tables_blob, tables->linker, x86ms->oem_id, x86ms->oem_table_id);',
                    '/* Hardened VM: build_waet(tables_blob, tables->linker, x86ms->oem_id, x86ms->oem_table_id); */'
                )
                patched = True
                print("[+] Commented out build_waet in acpi-build.c")

            # 2. Patch FADT C2/C3 latencies
            if '.plvl2_lat = 0xfff' in content:
                content = content.replace('.plvl2_lat = 0xfff', '.plvl2_lat = 101')
                patched = True
                print("[+] Patched plvl2_lat to 101 in acpi-build.c")
            if '.plvl3_lat = 0xfff' in content:
                content = content.replace('.plvl3_lat = 0xfff', '.plvl3_lat = 1001')
                patched = True
                print("[+] Patched plvl3_lat to 1001 in acpi-build.c")

            # 3. Patch slot naming S%.02X to RP%.02X
            if '"S%.02X"' in content or '"^S%.02X.PCNT"' in content:
                content = content.replace('"S%.02X"', '"RP%.02X"')
                content = content.replace('"^S%.02X.PCNT"', '"^RP%.02X.PCNT"')
                patched = True
                print("[+] Patched ACPI slot naming to RP%.02X in acpi-build.c")

        if 'acpi.c' in rel_path and ('seabios' in rel_path or 'seabios-hppa' in rel_path):
            if 'cpu_to_le16(0xfff)' in content:
                content = content.replace('fadt->plvl2_lat = cpu_to_le16(0xfff);', 'fadt->plvl2_lat = cpu_to_le16(101);')
                content = content.replace('fadt->plvl3_lat = cpu_to_le16(0xfff);', 'fadt->plvl3_lat = cpu_to_le16(1001);')
                patched = True
                print(f"[+] Patched FADT C2/C3 latencies in {rel_path}")

        if patched:
            with open(path, 'w') as f:
                f.write(content)
            print(f"[+] Patched {rel_path} — ACPI OEM IDs sanitized")


def patch_qemu_audio(base_dir):
    """Patch Intel HDA audio controller name strings."""
    path = os.path.join(base_dir, 'hw/audio/intel-hda.c')
    if not os.path.exists(path):
        print(f"[-] {path} not found — skipping audio patch")
        return
    with open(path, 'r') as f:
        content = f.read()

    if '"QEMU' in content:
        content = content.replace('"QEMU HDA"', '"Realtek ALC1220"')
        content = content.replace('"QEMU ICH9 HDA"', '"Realtek High Definition Audio"')
        with open(path, 'w') as f:
            f.write(content)
        print("[+] Patched hw/audio/intel-hda.c — audio device name sanitized")
    else:
        print("[*] hw/audio/intel-hda.c already patched or no matching strings")


def patch_qemu_net(base_dir):
    """Ensure e1000e uses correct Intel vendor attributes."""
    path = os.path.join(base_dir, 'hw/net/e1000e.c')
    if not os.path.exists(path):
        # Try the split-out file
        path = os.path.join(base_dir, 'hw/net/e1000e_core.c')
    if not os.path.exists(path):
        print(f"[-] e1000e source not found — skipping NIC patch")
        return
    with open(path, 'r') as f:
        content = f.read()

    # The e1000e already uses Intel IDs by default (0x8086 / 0x10d3)
    # but ensure no QEMU strings leak in descriptors
    if '"QEMU' in content or '"Red Hat' in content:
        content = content.replace('"QEMU"', '"Intel"')
        content = content.replace('"Red Hat"', '"Intel"')

    # Restore Device ID to 0x10D3 (standard Intel 82574L) for out-of-the-box Windows driver support
    if '0x1539' in content:
        content = content.replace('0x1539', '0x10D3')
    if 'c->device_id = E1000_DEV_ID_82574L;' in content:
        content = content.replace('c->device_id = E1000_DEV_ID_82574L;', 'c->device_id = 0x10D3; /* Intel 82574L */')
    if 'dc->desc = "Intel 82574L GbE Controller";' in content:
        content = content.replace('dc->desc = "Intel 82574L GbE Controller";', 'dc->desc = "Intel(R) 82574L Gigabit Network Connection";')
    if 'dc->desc = "Intel(R) I211 Gigabit Network Connection";' in content:
        content = content.replace('dc->desc = "Intel(R) I211 Gigabit Network Connection";', 'dc->desc = "Intel(R) 82574L Gigabit Network Connection";')

    # Spoof subsys_ven property default to 0x1043 (ASUS) and subsys to 0x85f0
    content = re.sub(r'(subsys_ven,\s*)PCI_VENDOR_ID_INTEL(\s*,\s*e1000e_prop_subsys_ven)', r'\g<1>0x1043\2', content)
    content = re.sub(r'(subsys,\s*)0(\s*,\s*e1000e_prop_subsys)', r'\g<1>0x85f0\2', content)

    with open(path, 'w') as f:
        f.write(content)
    print("[+] Patched e1000e — NIC vendor strings cleaned, spoofed to Intel 82574L with ASUS subsystem")

    # Restore device ID in e1000x_regs.h to 0x10D3 to ensure driver matching
    regs_path = os.path.join(base_dir, 'hw/net/e1000x_regs.h')
    if os.path.exists(regs_path):
        with open(regs_path, 'r') as f:
            regs_content = f.read()
        if '0x10F6' in regs_content:
            regs_content = regs_content.replace('0x10F6', '0x10D3')
            with open(regs_path, 'w') as f:
                f.write(regs_content)
            print("[+] Patched e1000x_regs.h — device ID changed back to 0x10D3")


def patch_qemu_machine_defaults(base_dir):
    """Sanitize default SMBIOS values in pc_q35.c and pc_piix.c."""
    patched_any = False
    for filename in ['hw/i386/pc_q35.c', 'hw/i386/pc_piix.c']:
        path = os.path.join(base_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, 'r') as f:
            content = f.read()
        
        patched = False
        old_smbios = 'smbios_set_defaults("QEMU", mc->desc,'
        new_smbios = 'smbios_set_defaults("ASUSTeK COMPUTER INC.", "ROG MAXIMUS Z790 HERO",'
        if old_smbios in content:
            content = content.replace(old_smbios, new_smbios)
            patched = True
            print(f"[+] Patched smbios_set_defaults in {filename}")

        if filename == 'hw/i386/pc_q35.c':
            old_desc = 'm->desc = "Standard PC (Q35 + ICH9, 2009)";'
            new_desc = 'm->desc = "Standard PC";'
            if old_desc in content:
                content = content.replace(old_desc, new_desc)
                patched = True
                print(f"[+] Patched machine description in {filename}")

        if patched:
            with open(path, 'w') as f:
                f.write(content)
            patched_any = True
            print(f"[+] Patched {filename} complete")


# ═══════════════════════════════════════════════════════════════════════
#  MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("Usage: patcher.py [kernel|qemu] <source_dir>")
        sys.exit(1)

    target = sys.argv[1]
    src_dir = sys.argv[2]

    if target == 'kernel':
        print("=" * 60)
        print("  Kernel Patcher — Hardened KVM Anti-Detection")
        print("=" * 60)
        patch_kernel_cpuid_c(src_dir)
        patch_kernel_svm_h(src_dir)
        patch_kernel_svm_c(src_dir)
        patch_kernel_vmx_h(src_dir)
        patch_kernel_vmx_c(src_dir)
        patch_kernel_x86_c(src_dir)
        print("=" * 60)
        print("  Kernel patching complete.")
        print("=" * 60)

    elif target == 'qemu':
        print("=" * 60)
        print("  QEMU Patcher — Hardware Emulation Hardening")
        print("=" * 60)
        patch_qemu_smbios(src_dir)
        patch_qemu_nvme(src_dir)
        patch_qemu_ide(src_dir)
        patch_qemu_scsi(src_dir)
        patch_qemu_pci_ids(src_dir)
        patch_qemu_acpi(src_dir)
        patch_qemu_audio(src_dir)
        patch_qemu_net(src_dir)
        patch_qemu_machine_defaults(src_dir)
        print("=" * 60)
        print("  QEMU patching complete.")
        print("=" * 60)

    else:
        print(f"Unknown target: {target}")
        print("Usage: patcher.py [kernel|qemu] <source_dir>")
        sys.exit(1)


if __name__ == "__main__":
    main()
