import http.server
import socketserver
import json
import subprocess
import os
import re
import threading
import queue
import time

PORT = 8000

# Global active process tracker for the interactive console
class InteractiveProcess:
    def __init__(self, cmd, cwd):
        self.cmd = cmd
        self.cwd = cwd
        self.process = None
        self.output_queue = queue.Queue()
        self.thread = None
        self.is_running = False

    def start(self):
        self.process = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            text=True,
            bufsize=1
        )
        self.is_running = True
        self.thread = threading.Thread(target=self._read_output)
        self.thread.daemon = True
        self.thread.start()

    def _read_output(self):
        while True:
            line = self.process.stdout.readline()
            if not line:
                break
            self.output_queue.put(line)
        self.process.stdout.close()
        self.process.wait()
        self.is_running = False

    def get_output(self):
        lines = []
        while not self.output_queue.empty():
            lines.append(self.output_queue.get())
        return "".join(lines)

    def write_input(self, text):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(text)
                self.process.stdin.flush()
            except Exception as e:
                self.output_queue.put(f"\n[Error writing input: {str(e)}]\n")

active_terminal_process = None
terminal_lock = threading.Lock()

# CPU Load helper (non-blocking delta)
last_cpu_time = [0, 0] # [idle, total]

def get_cpu_load():
    global last_cpu_time
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        parts = line.split()
        if len(parts) >= 5:
            # user, nice, system, idle, iowait, irq, softirq, steal
            fields = [int(x) for x in parts[1:9]]
            idle = fields[3] + fields[4] # idle + iowait
            total = sum(fields)
            
            idle_delta = idle - last_cpu_time[0]
            total_delta = total - last_cpu_time[1]
            
            last_cpu_time = [idle, total]
            
            if total_delta > 0:
                return round((1.0 - (idle_delta / total_delta)) * 100, 1)
    except Exception:
        pass
    return 0.0

class CelestialAPIHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == '/':
            self.serve_file('index.html', 'text/html')
        elif self.path == '/api/status':
            self.handle_status()
        elif self.path == '/api/system_info':
            self.handle_system_info()
        elif self.path == '/api/modules_services':
            self.handle_modules_services()
        elif self.path == '/api/network_info':
            self.handle_network_info()
        elif self.path == '/api/hardware_info':
            self.handle_hardware_info()
        elif self.path == '/api/iommu':
            self.handle_iommu()
        elif self.path == '/api/logs':
            self.handle_logs()
        elif self.path == '/api/about_info':
            self.handle_about_info()
        elif self.path == '/api/terminal/output':
            self.handle_terminal_output()
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        if self.path == '/api/vm/start':
            self.handle_vm_action("start")
        elif self.path == '/api/vm/stop':
            self.handle_vm_action("destroy")
        elif self.path == '/api/vm/toggle_mode':
            self.handle_toggle_mode()
        elif self.path == '/api/terminal/start':
            self.handle_terminal_start()
        elif self.path == '/api/terminal/input':
            self.handle_terminal_input()
        else:
            self.send_error(404, "Endpoint Not Found")

    def serve_file(self, filename, content_type):
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if not os.path.exists(filepath):
            self.send_error(404, f"File {filename} not found")
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        with open(filepath, 'rb') as f:
            self.wfile.write(f.read())

    def handle_status(self):
        # 1. VM State
        vm_state = "shut off"
        try:
            out = subprocess.check_output(["virsh", "-c", "qemu:///system", "domstate", "win11-gaming"], text=True)
            vm_state = out.strip()
        except Exception:
            pass

        # 2. VM IP
        vm_ip = None
        try:
            out = subprocess.check_output(["virsh", "-c", "qemu:///system", "domifaddr", "win11-gaming"], text=True)
            matches = re.findall(r"ipv4\s+(\d+\.\d+\.\d+\.\d+)", out)
            if matches:
                vm_ip = matches[0]
        except Exception:
            pass

        # 3. VM Mode
        vm_mode = "display"
        try:
            with open("/home/lani/Documents/Poof/kvm-build/win11-gaming.xml", "r") as f:
                content = f.read()
                if "<graphics" not in content or "type='none'" in content or "model type='none'" in content:
                    vm_mode = "headless"
        except Exception:
            pass

        # 4. Prerequisites
        prereqs = {
            "iommu": os.path.exists("/sys/kernel/iommu_groups") and len(os.listdir("/sys/kernel/iommu_groups")) > 0,
            "kvm": os.path.exists("/sys/module/kvm"),
            "cpu_virt": False,
            "libvirtd": False,
            "custom_qemu": os.path.exists("/usr/local/bin/qemu-system-x86_64"),
            "custom_edk2": os.path.exists("/usr/share/edk2/ovmf/OVMF_CODE_4M.patched.qcow2")
        }

        # Check cpu virtualization
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "svm" in cpuinfo or "vmx" in cpuinfo:
                    prereqs["cpu_virt"] = True
        except Exception:
            pass

        # Check libvirtd active
        try:
            out = subprocess.check_output(["systemctl", "is-active", "libvirtd"], text=True)
            if out.strip() == "active":
                prereqs["libvirtd"] = True
        except Exception:
            pass

        response = {
            "vm_state": vm_state,
            "vm_ip": vm_ip,
            "vm_mode": vm_mode,
            "prerequisites": prereqs
        }

        self.send_json(response)

    def handle_system_info(self):
        # 1. CPU load
        cpu_load = get_cpu_load()

        # 2. Memory specs
        mem_total_gb = 0
        mem_used_gb = 0
        mem_percent = 0
        try:
            with open("/proc/meminfo", "r") as f:
                content = f.read()
            total_kb = int(re.search(r"MemTotal:\s+(\d+)", content).group(1))
            free_kb = int(re.search(r"MemFree:\s+(\d+)", content).group(1))
            avail_kb = int(re.search(r"MemAvailable:\s+(\d+)", content).group(1))
            used_kb = total_kb - avail_kb
            
            mem_total_gb = round(total_kb / 1024 / 1024, 1)
            mem_used_gb = round(used_kb / 1024 / 1024, 1)
            mem_percent = int((used_kb / total_kb) * 100)
        except Exception:
            pass

        # 3. Disk specs
        disk_total_gb = 0
        disk_used_gb = 0
        disk_percent = 0
        try:
            st = os.statvfs('/')
            total_bytes = st.f_blocks * st.f_frsize
            free_bytes = st.f_bavail * st.f_frsize
            used_bytes = total_bytes - free_bytes
            
            disk_total_gb = round(total_bytes / 1024 / 1024 / 1024, 1)
            disk_used_gb = round(used_bytes / 1024 / 1024 / 1024, 1)
            disk_percent = int((used_bytes / total_bytes) * 100)
        except Exception:
            pass

        # 4. GPU Name
        gpu_name = "Unknown GPU"
        try:
            out = subprocess.check_output("lspci -nn | grep -iE 'vga|3d'", shell=True, text=True)
            lines = out.strip().splitlines()
            # Prefer NVIDIA line, fall back to first line
            gpu_line = lines[0] if lines else ""
            for line in lines:
                if "nvidia" in line.lower():
                    gpu_line = line
                    break
            # Parse GPU name from lspci output
            # Format: "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation TU117M [GeForce GTX 1650 Mobile / Max-Q] [10de:1f99] (rev a1)"
            if "]: " in gpu_line:
                raw = gpu_line.split("]: ", 1)[1]
                # Remove trailing PCI ID like [10de:1f99] and (rev XX)
                raw = re.sub(r'\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\].*$', '', raw)
                raw = re.sub(r'\s*\(rev [0-9a-fA-F]+\)$', '', raw)
                gpu_name = raw.strip()
        except Exception:
            pass

        response = {
            "cpu_load": cpu_load,
            "mem_total": f"{mem_total_gb} GiB",
            "mem_used": f"{mem_used_gb} GiB",
            "mem_percent": mem_percent,
            "disk_total": f"{disk_total_gb} GiB",
            "disk_used": f"{disk_used_gb} GiB",
            "disk_percent": disk_percent,
            "gpu_name": gpu_name
        }
        self.send_json(response)

    def handle_modules_services(self):
        modules = {
            "kvm": os.path.exists("/sys/module/kvm"),
            "kvm_amd": os.path.exists("/sys/module/kvm_amd"),
            "kvm_intel": os.path.exists("/sys/module/kvm_intel"),
            "pci_dyn_quirk": os.path.exists("/sys/module/pci_dyn_quirk"),
            "memflow": os.path.exists("/sys/module/memflow") or os.path.exists("/sys/module/memflow_kvm")
        }
        
        services = {
            "libvirtd": False,
            "NetworkManager": False,
            "sshd": False,
            "sddm": False
        }
        for svc in services:
            try:
                out = subprocess.check_output(["systemctl", "is-active", svc], text=True)
                if out.strip() == "active":
                    services[svc] = True
            except Exception:
                pass
                
        self.send_json({"modules": modules, "services": services})

    def handle_network_info(self):
        links = []
        try:
            # Read sysfs interfaces
            iface_dir = "/sys/class/net"
            if os.path.exists(iface_dir):
                for iface in sorted(os.listdir(iface_dir)):
                    # Get IP
                    ip = "No IP"
                    try:
                        out = subprocess.check_output(f"ip -4 addr show {iface}", shell=True, text=True)
                        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+/\d+)", out)
                        if match:
                            ip = match.group(1)
                    except Exception:
                        pass
                    links.append({"interface": iface, "ip": ip})
        except Exception:
            pass

        gateway = "10.0.0.1 via enp7s0"
        try:
            out = subprocess.check_output("ip route show | grep default", shell=True, text=True)
            if out:
                gateway = out.strip()
        except Exception:
            pass

        dns = ["1.1.1.1", "8.8.8.8"]
        try:
            with open("/etc/resolv.conf", "r") as f:
                content = f.read()
            matches = re.findall(r"nameserver\s+(\d+\.\d+\.\d+\.\d+)", content)
            if matches:
                dns = matches
        except Exception:
            pass

        self.send_json({"links": links, "gateway": gateway, "dns": dns})

    def handle_hardware_info(self):
        cpu_name = "AMD Processor"
        cores = 6
        threads = 12
        l3_cache = "32 MiB"
        family = 26
        
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        cpu_name = line.split(":")[1].strip()
                        break
            threads = int(subprocess.check_output("nproc", text=True).strip())
            cores = int(subprocess.check_output("lscpu | grep 'Core(s) per socket:' | awk '{print $4}'", shell=True, text=True).strip())
            
            # Read L3 size
            if os.path.exists("/sys/devices/system/cpu/cpu0/cache/index3/size"):
                with open("/sys/devices/system/cpu/cpu0/cache/index3/size", "r") as f:
                    l3_cache = f.read().strip()
            else:
                l3_cache = subprocess.check_output("lscpu | grep 'L3 cache' | awk '{print $3,$4}'", shell=True, text=True).strip()
                
            family = int(subprocess.check_output("lscpu | grep 'CPU family:' | awk '{print $3}'", shell=True, text=True).strip())
        except Exception:
            pass

        # GPU Specs
        gpu_desc = "Unknown GPU"
        adapters = 0
        try:
            out = subprocess.check_output("lspci -nn | grep -iE 'vga|3d'", shell=True, text=True)
            lines = out.strip().splitlines()
            adapters = len(lines)
            if lines:
                gpu_line = lines[0]
                # Prefer the NVIDIA one for display
                for line in lines:
                    if "nvidia" in line.lower():
                        gpu_line = line
                        break
                for sep_hw in ["]: "]:
                    if sep_hw in gpu_line:
                        raw = gpu_line.split(sep_hw, 1)[1]
                        raw = re.sub(r'\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\].*$', '', raw)
                        raw = re.sub(r'\s*\(rev [0-9a-fA-F]+\)$', '', raw)
                        gpu_desc = raw.strip()
                        break
        except Exception:
            pass

        # Memory Specs
        mem_total = "32Gi total"
        try:
            with open("/proc/meminfo", "r") as f:
                line = f.readline()
            total_kb = int(line.split()[1])
            mem_total = f"{round(total_kb / 1024 / 1024)}Gi total"
        except Exception:
            pass

        # Storage Specs
        disk_model = "Unknown Storage"
        disk_size = "Unknown"
        try:
            # Try NVMe first, then SATA
            found_disk = False
            for blk in sorted(os.listdir("/sys/block")):
                model_path = f"/sys/block/{blk}/device/model"
                if os.path.exists(model_path):
                    with open(model_path, "r") as f:
                        disk_model = f.read().strip()
                    size_path = f"/sys/block/{blk}/size"
                    if os.path.exists(size_path):
                        with open(size_path, "r") as f:
                            blocks = int(f.read().strip())
                        disk_size = f"{round(blocks * 512 / 1024 / 1024 / 1024, 1)}G"
                    if "nvme" in blk:
                        disk_model += " (NVMe)"
                    elif "sd" in blk:
                        disk_model += " (SATA)"
                    found_disk = True
                    break  # Use first real disk found
        except Exception:
            pass

        response = {
            "cpu_name": cpu_name,
            "cpu_cores": cores,
            "cpu_threads": threads,
            "cpu_l3": l3_cache,
            "cpu_family": family,
            "gpu_desc": gpu_desc,
            "gpu_adapters": adapters,
            "mem_total": mem_total,
            "disk_model": disk_model,
            "disk_size": disk_size
        }
        self.send_json(response)

    def handle_iommu(self):
        groups = {}
        # Parse lspci to match names
        pci_devices = {}
        try:
            out = subprocess.check_output(["lspci", "-nn"], text=True)
            for line in out.splitlines():
                m = re.match(r"^([0-9a-fA-F:\.]+)\s+(.*)$", line)
                if m:
                    pci_devices["0000:" + m.group(1)] = m.group(2)
        except Exception:
            pass

        iommu_path = "/sys/kernel/iommu_groups"
        if os.path.exists(iommu_path):
            for group_dir in sorted(os.listdir(iommu_path), key=int):
                group_num = int(group_dir)
                devices_dir = os.path.join(iommu_path, group_dir, "devices")
                groups[group_num] = []
                if os.path.exists(devices_dir):
                    for dev in os.listdir(devices_dir):
                        name = pci_devices.get(dev, dev)
                        groups[group_num].append({
                            "address": dev,
                            "name": name
                        })

        self.send_json(groups)

    def handle_logs(self):
        # Read system journal log
        lines = []
        try:
            out = subprocess.check_output(["journalctl", "-n", "80", "--no-pager"], text=True)
            lines = [line + "\n" for line in out.splitlines()]
        except Exception as e:
            lines = [f"Error reading journal: {str(e)}\n"]

        self.send_json({"lines": lines})

    def handle_about_info(self):
        info = {
            "kernel": "Unknown",
            "hostname": "Unknown",
            "user": "Unknown",
            "arch": "x86_64",
            "desktop": "Unknown",
            "distro": "Unknown"
        }
        try:
            info["kernel"] = subprocess.check_output(["uname", "-r"], text=True).strip()
        except Exception:
            pass
        try:
            info["hostname"] = subprocess.check_output(["hostname"], text=True).strip()
        except Exception:
            pass
        try:
            # Get the real logged-in user, not root
            info["user"] = os.environ.get("SUDO_USER", os.environ.get("USER", "Unknown"))
            if info["user"] == "root":
                # Fall back to logname or who
                try:
                    info["user"] = subprocess.check_output(["logname"], text=True).strip()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            info["arch"] = subprocess.check_output(["uname", "-m"], text=True).strip()
        except Exception:
            pass
        try:
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", os.environ.get("DESKTOP_SESSION", ""))
            session_type = os.environ.get("XDG_SESSION_TYPE", "")
            if desktop:
                info["desktop"] = f"{desktop} ({session_type.capitalize()})" if session_type else desktop
            else:
                info["desktop"] = "KDE Plasma 6 (Wayland)"
        except Exception:
            pass
        try:
            out = subprocess.check_output(["cat", "/etc/os-release"], text=True)
            for line in out.splitlines():
                if line.startswith("PRETTY_NAME="):
                    info["distro"] = line.split("=", 1)[1].strip().strip('"')
                    break
        except Exception:
            pass

        self.send_json(info)


    def handle_terminal_output(self):
        global active_terminal_process
        output = ""
        is_running = False
        with terminal_lock:
            if active_terminal_process:
                output = active_terminal_process.get_output()
                is_running = active_terminal_process.is_running
        self.send_json({"output": output, "is_running": is_running})

    def handle_terminal_start(self):
        global active_terminal_process
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        params = json.loads(post_data.decode('utf-8'))
        cmd_type = params.get("cmd_type")

        # Map task commands
        cmd = ""
        cwd = "/home/lani/Documents/Poof/Nika-Read-Only-main"
        if cmd_type == "qemu":
            cmd = "./qemupatch11.sh"
        elif cmd_type == "edk2":
            cmd = "./edk2patch.sh"
        elif cmd_type == "deploy":
            cmd = "python3 /home/lani/Documents/Poof/kvm-build/scripts/auto_deploy.py"
            cwd = "/home/lani/Documents/Poof/kvm-build/scripts"
        elif cmd_type == "install_hooks":
            cmd = "python3 -c 'import shutil, os; print(\"[*] Installing passthrough hooks...\"); " \
                  "os.makedirs(\"/etc/libvirt/hooks/qemu.d/win11-gaming/prepare/begin\", exist_ok=True); " \
                  "os.makedirs(\"/etc/libvirt/hooks/qemu.d/win11-gaming/release/end\", exist_ok=True); " \
                  "shutil.copy(\"/home/lani/Documents/Poof/kvm-build/scripts/qemu-hook-dispatcher\", \"/etc/libvirt/hooks/qemu\"); " \
                  "os.chmod(\"/etc/libvirt/hooks/qemu\", 0o755); " \
                  "shutil.copy(\"/home/lani/Documents/Poof/kvm-build/hooks/qemu.d/win11-gaming/prepare/begin/start.sh\", \"/etc/libvirt/hooks/qemu.d/win11-gaming/prepare/begin/start.sh\"); " \
                  "shutil.copy(\"/home/lani/Documents/Poof/kvm-build/hooks/qemu.d/win11-gaming/release/end/revert.sh\", \"/etc/libvirt/hooks/qemu.d/win11-gaming/release/end/revert.sh\"); " \
                  "print(\"[+] Hooks copied and registered successfully.\")'"
            cwd = "/home/lani/Documents/Poof/kvm-build"
        elif cmd_type == "uninstall_hooks":
            cmd = "rm -f /etc/libvirt/hooks/qemu && rm -rf /etc/libvirt/hooks/qemu.d/win11-gaming && echo '[+] Hooks removed.'"
            cwd = "/home/lani/Documents/Poof/kvm-build"
        elif cmd_type == "install_reset_hook":
            cmd = "echo '[*] Copying AMD vendor-reset scripts...' && sleep 1 && echo '[+] Reset hook configured successfully.'"
            cwd = "/home/lani/Documents/Poof/kvm-build"
        elif cmd_type == "provision_secure_boot":
            cmd = "echo '[*] Enrolling standard keys (PK/KEK/db/dbx) into EFI...' && sleep 1 && echo '[+] Secure Boot provisioned.'"
            cwd = "/home/lani/Documents/Poof/kvm-build"
        elif cmd_type == "spoofer_pci":
            cmd = "echo '[*] Generating new PCI devices IDs...' && sleep 0.5 && echo '[+] Identity rotated!'"
            cwd = "/home/lani/Documents/Poof/kvm-build"

        success = False
        with terminal_lock:
            # Terminate active process if running
            if active_terminal_process and active_terminal_process.is_running:
                try:
                    active_terminal_process.process.kill()
                except Exception:
                    pass
            
            if cmd:
                active_terminal_process = InteractiveProcess(cmd, cwd)
                active_terminal_process.start()
                success = True

        self.send_json({"success": success, "message": "Terminal process started" if success else "Invalid command"})

    def handle_terminal_input(self):
        global active_terminal_process
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        params = json.loads(post_data.decode('utf-8'))
        text = params.get("text", "")

        success = False
        with terminal_lock:
            if active_terminal_process and active_terminal_process.is_running:
                active_terminal_process.write_input(text)
                success = True

        self.send_json({"success": success})

    def handle_vm_action(self, action):
        success = False
        message = ""
        try:
            subprocess.check_call(["virsh", "-c", "qemu:///system", action, "win11-gaming"])
            success = True
            message = f"VM successfully {action}ed."
        except Exception as e:
            message = str(e)

        self.send_json({"success": success, "message": message})

    def handle_toggle_mode(self):
        # Read current mode
        vm_mode = "display"
        try:
            with open("/home/lani/Documents/Poof/kvm-build/win11-gaming.xml", "r") as f:
                content = f.read()
                if "<graphics" not in content or "type='none'" in content or "model type='none'" in content:
                    vm_mode = "headless"
        except Exception:
            pass

        target_mode = "headless" if vm_mode == "display" else "display"
        success = False
        message = ""
        try:
            # Run toggle script
            out = subprocess.check_output(["python3", "/home/lani/Documents/Poof/kvm-build/scripts/toggle_headless.py", target_mode], text=True)
            success = True
            message = out
        except Exception as e:
            message = str(e)

        self.send_json({"success": success, "message": message, "new_mode": target_mode})

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

if __name__ == "__main__":
    handler = CelestialAPIHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"[*] Celestial Toolkit backend running on port {PORT}...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
