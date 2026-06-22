import subprocess
import re
import sys

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ["headless", "display"]:
        print("Usage: python toggle_headless.py [headless|display]")
        sys.exit(1)
        
    mode = sys.argv[1]

    # Read the golden base XML (current.xml has working SATA disks + UUID)
    with open("/home/lani/Documents/Poof/kvm-build/current.xml", "r") as f:
        xml_content = f.read()

    # Remove the runtime 'id' attribute from <domain> 
    xml_content = re.sub(r"<domain type='kvm' id='\d+'", "<domain type='kvm'", xml_content)

    # Remove runtime-only elements
    xml_content = re.sub(r"\s*<resource>.*?</resource>", "", xml_content, flags=re.DOTALL)
    xml_content = re.sub(r"\s*<seclabel.*?</seclabel>", "", xml_content, flags=re.DOTALL)
    xml_content = re.sub(r"\s*<alias name='[^']*'/>", "", xml_content)
    xml_content = re.sub(r"\s*<backingStore/>", "", xml_content)
    xml_content = re.sub(r" index='\d+'", "", xml_content)
    xml_content = re.sub(r"\s*<target dev='vnet\d+'/>", "", xml_content)
    xml_content = re.sub(r" portid='[^']*'", "", xml_content)
    xml_content = re.sub(r" bridge='[^']*'", "", xml_content)

    # ===== NIKA FIX 1: Replace entire <features> block =====
    # Turn ALL Hyper-V enlightenments OFF (Nika's exact config)
    nika_features = """<features>
    <acpi/>
    <apic/>
    <hyperv mode="custom">
      <relaxed state="off"/>
      <vapic state="off"/>
      <spinlocks state="off"/>
      <vpindex state="off"/>
      <runtime state="off"/>
      <synic state="off"/>
      <stimer state="off"/>
      <reset state="off"/>
      <vendor_id state="off"/>
      <frequencies state="off"/>
      <reenlightenment state="off"/>
      <tlbflush state="off"/>
      <ipi state="off"/>
      <evmcs state="off"/>
      <avic state="off"/>
    </hyperv>
    <kvm>
      <hidden state="on"/>
    </kvm>
    <ioapic driver="kvm"/>
    <msrs unknown="fault"/>
    <pmu state="on"/>
    <smm state="on"/>
    <vmport state="off"/>
    <ps2 state="on"/>
  </features>"""
    xml_content = re.sub(r"<features>.*?</features>", nika_features, xml_content, flags=re.DOTALL)
    print("Fixed: Hyper-V enlightenments ALL OFF (Nika config)")

    # ===== NIKA FIX 2: CPU section with proper features =====
    nika_cpu = """<cpu mode='host-passthrough' check='none' migratable='off'>
    <topology sockets='1' dies='1' cores='6' threads='2'/>
    <cache mode='passthrough'/>
    <feature policy='disable' name='hypervisor'/>
    <feature policy='require' name='svm'/>
    <feature policy='disable' name='x2apic'/>
    <feature policy='require' name='topoext'/>
  </cpu>"""
    xml_content = re.sub(r"<cpu.*?</cpu>", nika_cpu, xml_content, flags=re.DOTALL)
    print("Fixed: CPU section (Nika config with svm, topoext)")

    # ===== NIKA FIX 3: Clock - disable kvmclock AND hypervclock =====
    nika_clock = """<clock offset='localtime'>
    <timer name='tsc' present='yes' tickpolicy='discard' mode='native'/>
    <timer name='hpet' present='yes'/>
    <timer name='rtc' present='yes'/>
    <timer name='pit' present='yes'/>
    <timer name='kvmclock' present='no'/>
    <timer name='hypervclock' present='no'/>
  </clock>"""
    xml_content = re.sub(r"<clock.*?</clock>", nika_clock, xml_content, flags=re.DOTALL)
    print("Fixed: Clock (kvmclock=no, hypervclock=no, tsc native)")

    # ===== NIKA FIX 4: Remove looking-glass ivshmem =====
    xml_content = re.sub(r"\s*<shmem name='looking-glass'>.*?</shmem>", "", xml_content, flags=re.DOTALL)
    print("Fixed: Removed looking-glass ivshmem device")

    # ===== NIKA FIX 5: Replace ACPI tables with ssdt1 + ssdt2 =====
    # Remove old acpitable entries
    xml_content = re.sub(r"\s*<qemu:arg value='-acpitable'/>", "", xml_content)
    xml_content = re.sub(r"\s*<qemu:arg value='file=/var/lib/libvirt/roms/ssdt\.aml'/>", "", xml_content)
    # Add Nika's ssdt1 + ssdt2 before </qemu:commandline>
    ssdt_args = """    <qemu:arg value='-acpitable'/>
    <qemu:arg value='file=/usr/local/bin/ssdt1.aml'/>
    <qemu:arg value='-acpitable'/>
    <qemu:arg value='file=/usr/local/bin/ssdt2.aml'/>
  </qemu:commandline>"""
    xml_content = xml_content.replace("</qemu:commandline>", ssdt_args)
    print("Fixed: ACPI tables (ssdt1.aml + ssdt2.aml)")

    # ===== HEADLESS / DISPLAY MODE =====
    if mode == "headless":
        xml_content = re.sub(r"\s*<graphics.*?</graphics>", "", xml_content, flags=re.DOTALL)
        xml_content = re.sub(r"<video>.*?</video>", "<video>\n      <model type='none'/>\n    </video>", xml_content, flags=re.DOTALL)
        print("Mode: headless (graphics removed, video=none)")
    else:
        if "<graphics" not in xml_content:
            video_qxl = """<graphics type='spice' autoport='yes' listen='127.0.0.1'>
      <listen type='address' address='127.0.0.1'/>
    </graphics>
    <video>
      <model type='qxl' ram='65536' vram='65536' vgamem='16384' heads='1' primary='yes'/>
    </video>"""
            xml_content = re.sub(r"<video>.*?</video>", video_qxl, xml_content, flags=re.DOTALL)
        print("Mode: display (graphics=spice, video=qxl)")

    output_path = "/home/lani/Documents/Poof/kvm-build/win11-gaming-toggled.xml"
    with open(output_path, "w") as f:
        f.write(xml_content)

    subprocess.check_call(["virsh", "-c", "qemu:///system", "define", output_path])
    print("VM redefined successfully.")
    
    try:
        subprocess.check_call(["virsh", "-c", "qemu:///system", "destroy", "win11-gaming"])
    except:
        pass
    subprocess.check_call(["virsh", "-c", "qemu:///system", "start", "win11-gaming"])
    print(f"VM successfully restarted in {mode} mode.")

if __name__ == "__main__":
    main()
