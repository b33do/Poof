import subprocess
import xml.etree.ElementTree as ET

def patch_xml():
    # 1. Dump the current XML
    xml_data = subprocess.check_output(["virsh", "-c", "qemu:///system", "dumpxml", "win11-gaming"]).decode("utf-8")
    root = ET.fromstring(xml_data)

    # 2. Modify CPU section
    cpu = root.find("cpu")
    if cpu is not None:
        cpu.set("migratable", "off")
        
        # Ensure cache mode='passthrough'
        cache = cpu.find("cache")
        if cache is None:
            cache = ET.SubElement(cpu, "cache")
        cache.set("mode", "passthrough")
        
        # Ensure features
        features_to_set = {
            "hypervisor": "disable",
            "svm": "require",
            "x2apic": "disable",
            "topoext": "require"
        }
        
        # Remove existing features that we want to manage to avoid duplicates
        for feature in list(cpu.findall("feature")):
            if feature.get("name") in features_to_set:
                cpu.remove(feature)
                
        # Add the features with correct policies
        for name, policy in features_to_set.items():
            f = ET.SubElement(cpu, "feature")
            f.set("policy", policy)
            f.set("name", name)

    # 2.5 Modify Hyper-V vendor ID for AMD compatibility
    features_el = root.find("features")
    if features_el is not None:
        hyperv = features_el.find("hyperv")
        if hyperv is not None:
            vendor_id = hyperv.find("vendor_id")
            if vendor_id is not None:
                vendor_id.set("value", "AuthenticAMD")

    devices = root.find("devices")
    if devices is None:
        print("Error: <devices> section not found in XML")
        return

    # 3. Modify Disk: change virtio to sata
    for disk in devices.findall("disk"):
        if disk.get("device") == "disk":
            # Change target
            target = disk.find("target")
            if target is not None:
                target.set("dev", "sda")
                target.set("bus", "sata")
            
            # Change address
            address = disk.find("address")
            if address is not None:
                address.clear()
                address.set("type", "drive")
                address.set("controller", "0")
                address.set("bus", "0")
                address.set("target", "0")
                address.set("unit", "0")
            
            # Ensure serial exists
            serial = disk.find("serial")
            if serial is None:
                serial = ET.SubElement(disk, "serial")
                serial.text = "S3FNX0GB418903Y"

    # 4. Remove virtio-serial controller
    for controller in devices.findall("controller"):
        if controller.get("type") == "virtio-serial":
            devices.remove(controller)

    # 4.5 Remove pcie-to-pci-bridge controller to clean up virtual PCI bridges
    for controller in list(devices.findall("controller")):
        if controller.get("type") == "pci" and controller.get("model") == "pcie-to-pci-bridge":
            devices.remove(controller)

    # 5. Remove unix channel (guest agent)
    for channel in devices.findall("channel"):
        if channel.get("type") == "unix":
            devices.remove(channel)

    # 5.5 Change network interface model to e1000e (with patched Device ID to bypass blacklist and virtual PCI vendor checks)
    for interface in devices.findall("interface"):
        model = interface.find("model")
        if model is not None:
            model.set("type", "e1000e")

    # 6. Disable memballoon
    memballoon = devices.find("memballoon")
    if memballoon is not None:
        memballoon.clear()
        memballoon.set("model", "none")

    # 7. Restore video graphics card (QXL) temporarily to allow Virt-Manager display
    video = devices.find("video")
    if video is not None:
        video.clear()
        model = ET.SubElement(video, "model")
        model.set("type", "qxl")
        model.set("ram", "65536")
        model.set("vram", "65536")
        model.set("vgamem", "16384")
        model.set("heads", "1")
        model.set("primary", "yes")

    # 7.5 Modify looking-glass shmem address to avoid virtual PCI bridge
    for shmem in devices.findall("shmem"):
        if shmem.get("name") == "looking-glass":
            address = shmem.find("address")
            if address is not None:
                address.clear()
                address.set("type", "pci")
                address.set("domain", "0x0000")
                address.set("bus", "0x00")
                address.set("slot", "0x10")
                address.set("function", "0x0")

    # 7.6 Update firmware loader and nvram to point to patched OVMF/EDK2 files
    os_element = root.find("os")
    # Remove firmware attribute if it exists to allow custom loader
    if "firmware" in os_element.attrib:
        del os_element.attrib["firmware"]
        
    # Remove firmware sub-element if it exists
    firmware_el = os_element.find("firmware")
    if firmware_el is not None:
        os_element.remove(firmware_el)

    loader = os_element.find("loader")
    if loader is None:
        loader = ET.SubElement(os_element, "loader")
    loader.clear()
    loader.set("readonly", "yes")
    loader.set("secure", "yes")
    loader.set("type", "pflash")
    loader.set("format", "qcow2")
    loader.text = "/usr/share/edk2/ovmf/OVMF_CODE_4M.patched.qcow2"
    
    nvram = os_element.find("nvram")
    if nvram is None:
        nvram = ET.SubElement(os_element, "nvram")
    nvram.clear()
    nvram.set("format", "qcow2")
    nvram.text = "/usr/share/edk2/ovmf/OVMF_VARS_4M.patched.qcow2"

    # 7.7 Ensure power management properties exist to bypass power capabilities check
    pm = root.find("pm")
    if pm is None:
        pm = ET.SubElement(root, "pm")
    pm.clear()
    suspend_to_mem = ET.SubElement(pm, "suspend-to-mem")
    suspend_to_mem.set("enabled", "yes")
    suspend_to_disk = ET.SubElement(pm, "suspend-to-disk")
    suspend_to_disk.set("enabled", "yes")

    # 7.8 Ensure HPET is present='yes' in clock to bypass system timers check
    clock = root.find("clock")
    if clock is not None:
        hpet = clock.find("./timer[@name='hpet']")
        if hpet is not None:
            hpet.set("present", "yes")
        else:
            hpet = ET.SubElement(clock, "timer")
            hpet.set("name", "hpet")
            hpet.set("present", "yes")

    # 7.9 Force hpet=on in qemu:commandline to override libvirt's automatic hpet=off default
    qemu_cmd = root.find("{http://libvirt.org/schemas/domain/qemu/1.0}commandline")
    if qemu_cmd is not None:
        args = qemu_cmd.findall("{http://libvirt.org/schemas/domain/qemu/1.0}arg")
        machine_found = False
        for i in range(len(args) - 1):
            if args[i].get("value") == "-machine":
                val = args[i+1].get("value")
                if "hpet=on" not in val:
                    args[i+1].set("value", val + ",hpet=on")
                machine_found = True
                break
        if not machine_found:
            arg1 = ET.SubElement(qemu_cmd, "{http://libvirt.org/schemas/domain/qemu/1.0}arg")
            arg1.set("value", "-machine")
            arg2 = ET.SubElement(qemu_cmd, "{http://libvirt.org/schemas/domain/qemu/1.0}arg")
            arg2.set("value", "hpet=on")

    # 8. Redefine the VM
    new_xml = ET.tostring(root, encoding="utf-8").decode("utf-8")
    with open("/home/lani/Documents/Poof/kvm-build/tmp/win11-gaming-patched.xml", "w") as f:
        f.write(new_xml)

    subprocess.check_call(["virsh", "-c", "qemu:///system", "define", "/home/lani/Documents/Poof/kvm-build/tmp/win11-gaming-patched.xml"])
    print("[+] VM XML patched and defined successfully.")

if __name__ == "__main__":
    patch_xml()
