import xml.etree.ElementTree as ET
import subprocess
import os

def main():
    ET.register_namespace('qemu', 'http://libvirt.org/schemas/domain/qemu/1.0')
    xml_output = subprocess.check_output(["virsh", "-c", "qemu:///system", "dumpxml", "win11-gaming"]).decode("utf-8")
    tmp_xml_path = "/home/lani/Documents/Poof/kvm-build/win11-gaming.xml.tmp.add"
    with open(tmp_xml_path, "w") as f:
        f.write(xml_output)

    try:
        tree = ET.parse(tmp_xml_path)
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return
        
    root = tree.getroot()
    if 'xmlns:qemu' not in root.attrib:
        # We don't need to manually add it if register_namespace worked, 
        # but if the dumpxml lacked it we might need to be careful.
        pass

    devices = root.find("devices")
    if devices is not None:
        # Check if graphics already exists
        if devices.find("graphics") is None:
            graphics = ET.SubElement(devices, "graphics")
            graphics.set("type", "spice")
            graphics.set("autoport", "yes")
            graphics.set("listen", "127.0.0.1")
            
            listen = ET.SubElement(graphics, "listen")
            listen.set("type", "address")
            listen.set("address", "127.0.0.1")
            print("Added <graphics type='spice'>")
        
        # Change video model back to qxl
        video = devices.find("video")
        if video is not None:
            model = video.find("model")
            if model is not None:
                model.set("type", "qxl")
                model.set("ram", "65536")
                model.set("vram", "65536")
                model.set("vgamem", "16384")
                model.set("heads", "1")
                model.set("primary", "yes")
                print("Set <video> model type back to 'qxl'")
        else:
            video = ET.SubElement(devices, "video")
            model = ET.SubElement(video, "model")
            model.set("type", "qxl")
            model.set("ram", "65536")
            model.set("vram", "65536")
            model.set("vgamem", "16384")
            model.set("heads", "1")
            model.set("primary", "yes")
            print("Added <video> with 'qxl'")

    patched_xml_path = "/home/lani/Documents/Poof/kvm-build/win11-gaming.xml.patched.add"
    tree.write(patched_xml_path, encoding="utf-8", xml_declaration=True)
    print(f"Patched XML saved to {patched_xml_path}")

    subprocess.check_call(["virsh", "-c", "qemu:///system", "define", patched_xml_path])
    print("VM redefined successfully in libvirt with display.")

    try:
        subprocess.check_call(["virsh", "-c", "qemu:///system", "destroy", "win11-gaming"])
    except subprocess.CalledProcessError:
        pass # VM might already be stopped

    subprocess.check_call(["virsh", "-c", "qemu:///system", "start", "win11-gaming"])
    print("VM win11-gaming started with virtual display.")

if __name__ == "__main__":
    main()
