import xml.etree.ElementTree as ET
import subprocess
import sys

def main():
    ET.register_namespace('qemu', 'http://libvirt.org/schemas/domain/qemu/1.0')
    
    # We will use the original untouched XML from kvm-build/win11-gaming.xml
    # since it has all the spoofing intact, and just remove the graphics from it.
    original_xml_path = "/home/lani/Documents/Poof/kvm-build/win11-gaming.xml"
    
    try:
        tree = ET.parse(original_xml_path)
    except Exception as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)
        
    root = tree.getroot()
    
    # Preserve UUID from libvirt if it's missing in original
    uuid_element = root.find("uuid")
    if uuid_element is None:
        u = ET.SubElement(root, "uuid")
        u.text = "51559a9c-8ef8-433e-9411-b4fa2bf92370"
        print("Added UUID to match libvirt")
        
    devices = root.find("devices")
    
    # Ensure OS has boot dev='hd'
    os_element = root.find("os")
    if os_element is not None:
        boot_element = os_element.find("boot")
        if boot_element is None:
            b = ET.SubElement(os_element, "boot")
            b.set("dev", "hd")
            print("Added <boot dev='hd'/> to OS")
    if devices is not None:
        # 1. Remove all <graphics> elements
        graphics_elements = devices.findall("graphics")
        for g in graphics_elements:
            devices.remove(g)
            print("Removed <graphics> element")

        # 2. Modify <video> element to model type='none'
        video = devices.find("video")
        if video is not None:
            video.clear()
            model = ET.SubElement(video, "model")
            model.set("type", "none")
            print("Set <video> model type to 'none'")
        else:
            video = ET.SubElement(devices, "video")
            model = ET.SubElement(video, "model")
            model.set("type", "none")
            print("Added <video> model type='none'")

        # 3. Remove all <audio> elements
        audio_elements = devices.findall("audio")
        for a in audio_elements:
            devices.remove(a)
            print("Removed <audio> element")

        # 4. Explicitly disable memballoon
        memballoon = devices.find("memballoon")
        if memballoon is not None:
            memballoon.set("model", "none")
            print("Set <memballoon> model to 'none'")
        else:
            mb = ET.SubElement(devices, "memballoon")
            mb.set("model", "none")
            print("Added <memballoon model='none'/>")

    patched_xml_path = "/home/lani/Documents/Poof/kvm-build/win11-gaming-headless.xml"
    tree.write(patched_xml_path, encoding="utf-8", xml_declaration=True)
    print(f"Patched headless XML saved to {patched_xml_path}")

    subprocess.check_call(["virsh", "-c", "qemu:///system", "define", patched_xml_path])
    print("VM redefined successfully in libvirt.")

    # Stop and start the VM
    try:
        subprocess.check_call(["virsh", "-c", "qemu:///system", "destroy", "win11-gaming"])
    except:
        pass
    
    subprocess.check_call(["virsh", "-c", "qemu:///system", "start", "win11-gaming"])
    print("VM win11-gaming started headlessly successfully with spoofing intact.")

if __name__ == "__main__":
    main()
