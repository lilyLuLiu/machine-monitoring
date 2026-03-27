import time
from proxyJump import SSHViaJump, SSHDirect, LocalShell

def setup_client(MONITOR_REMOTE, MONITOR_REMOTE_JUMP):
    """Sets up the client for monitoring (remote or local)."""
    if MONITOR_REMOTE.get('enabled'):
        if MONITOR_REMOTE_JUMP.get('enabled'):
            client = SSHViaJump(
                remote_host=MONITOR_REMOTE.get('HostName'),
                remote_user=MONITOR_REMOTE.get('User'),
                remote_key_path_on_jump=MONITOR_REMOTE.get('IdentityFile'),
                remote_port=MONITOR_REMOTE.get('Port', 22),
                jump_host=MONITOR_REMOTE_JUMP.get('HostName'),
                jump_user=MONITOR_REMOTE_JUMP.get('User'),
                jump_key_path=MONITOR_REMOTE_JUMP.get('IdentityFile'),
                jump_port=MONITOR_REMOTE_JUMP.get('Port', 22),
            )
            HOST_ALIAS = MONITOR_REMOTE.get('HostName') + " (via " + MONITOR_REMOTE_JUMP.get('HostName') + ")"
        else:
            client = SSHDirect(
                host=MONITOR_REMOTE.get('HostName'),
                user=MONITOR_REMOTE.get('User'),
                key_path=MONITOR_REMOTE.get('IdentityFile'),
                port=MONITOR_REMOTE.get('Port', 22),
            )
            HOST_ALIAS = MONITOR_REMOTE.get('HostName', 'RemoteHost')
    else:
        client = LocalShell()
        HOST_ALIAS = "localhost"
    return client, HOST_ALIAS

class MetricsCollector:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.prev_net = None

    def get_cpu(self):
        _, stdout, _ = self.client.run("top -b -n1 | grep '%Cpu' | awk '{print $2 + $4}'")
        line = stdout.strip()
        return float(line.replace(',', '.')) if line else 0.0

    def get_mem(self):
        _, stdout, _ = self.client.run("free | grep Mem | awk '{print ($3/$2) * 100}'")
        line = stdout.strip()
        return float(line.replace(',', '.')) if line else 0.0

    def get_disk_usage(self):
        _, stdout, _ = self.client.run("df -h / | awk 'NR==2 {print $5}' | tr -d '%'")
        line = stdout.strip()
        return float(line) if line else 0.0

    def get_disk_io(self):
        cmd = f"iostat -d -x 1 2 | grep {self.config['DISK_DEVICE']} | tail -1 | awk '{{print $NF}}'"
        _, stdout, _ = self.client.run(cmd)
        line = stdout.strip()
        return float(line) if line else 0.0

    def get_network(self):
        cmd = f"cat /proc/net/dev | grep {self.config['NET_INTERFACE']} | awk '{{print $2, $10}}'"
        _, stdout, _ = self.client.run(cmd)
        net_line = stdout.strip()
        if net_line:
            recv_bytes, sent_bytes = map(int, net_line.split())
            if self.prev_net is not None:
                recv_rate = (recv_bytes - self.prev_net[0]) / self.config['INTERVAL']
                sent_rate = (sent_bytes - self.prev_net[1]) / self.config['INTERVAL']
            else:
                recv_rate, sent_rate = 0.0, 0.0
            self.prev_net = (recv_bytes, sent_bytes)
            return {'net_recv': recv_rate, 'net_sent': sent_rate}
        return {'net_recv': 0.0, 'net_sent': 0.0}

    def get_load(self):
        _, stdout, _ = self.client.run("uptime | awk -F'load average:' '{print $2}' | awk '{print $1,$2,$3}'")
        load_line = stdout.strip()
        if load_line:
            loads = load_line.replace(',', ' ').split()
            if len(loads) >= 3:
                return {'load1': float(loads[0]), 'load5': float(loads[1]), 'load15': float(loads[2])}
        return {'load1': 0.0, 'load5': 0.0, 'load15': 0.0}

    def get_processes(self):
        _, stdout, _ = self.client.run("ps aux | wc -l")
        proc_line = stdout.strip()
        return int(proc_line) if proc_line else 0

    def collect_all_metrics(self, data):
        """Collects all enabled metrics and appends them to the data dictionary."""
        if self.config.get('MONITOR_CPU'):
            data['cpu'].append(self.get_cpu())
        if self.config.get('MONITOR_MEM'):
            data['mem'].append(self.get_mem())
        if self.config.get('MONITOR_DISK_USAGE'):
            data['disk_usage'].append(self.get_disk_usage())
        if self.config.get('MONITOR_DISK_IO'):
            data['disk_io'].append(self.get_disk_io())
        if self.config.get('MONITOR_NETWORK'):
            net_data = self.get_network()
            data['net_sent'].append(net_data['net_sent'])
            data['net_recv'].append(net_data['net_recv'])
        if self.config.get('MONITOR_LOAD'):
            load_data = self.get_load()
            data['load1'].append(load_data['load1'])
            data['load5'].append(load_data['load5'])
            data['load15'].append(load_data['load15'])
        if self.config.get('MONITOR_PROCESSES'):
            data['processes'].append(self.get_processes())


import matplotlib.pyplot as plt
from IPython.display import clear_output

def draw_plots(times, data, config, host_alias):
    clear_output(wait=True)
    
    enabled_metrics = [k for k, v in config.items() if k.startswith('MONITOR_') and v]
    n_plots = len(enabled_metrics)
    if n_plots == 0:
        print("No monitoring metrics enabled. Please modify the configuration.")
        return

    fig = plt.figure(figsize=(14, 2.5 * n_plots))
    gs = fig.add_gridspec(n_plots, 1, hspace=0.5)
    plot_idx = 0
    
    if config.get('MONITOR_CPU'):
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['cpu'], 'r-', linewidth=1.5)
        ax.set_ylabel('CPU (%)')
        ax.set_ylim(0, 100)
        ax.grid(True)
        ax.set_title('CPU Usage')
        plot_idx += 1
        
    if config.get('MONITOR_MEM'):
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['mem'], 'g-', linewidth=1.5)
        ax.set_ylabel('Memory (%)')
        ax.set_ylim(0, 100)
        ax.grid(True)
        ax.set_title('Memory Usage')
        plot_idx += 1

    if config.get('MONITOR_DISK_USAGE'):
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['disk_usage'], 'b-', linewidth=1.5)
        ax.set_ylabel('Disk Usage (%)')
        ax.set_ylim(0, 100)
        ax.grid(True)
        ax.set_title('Root Disk Usage')
        plot_idx += 1

    if config.get('MONITOR_DISK_IO'):
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['disk_io'], 'orange', linewidth=1.5)
        ax.set_ylabel('Disk I/O %util')
        ax.set_ylim(0, 100)
        ax.grid(True)
        ax.set_title(f'Disk I/O ({config["DISK_DEVICE"]})')
        plot_idx += 1

    if config.get('MONITOR_NETWORK') and len(data['net_sent']) > 0:
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['net_sent'], 'c-', label='Sent', linewidth=1.5)
        ax.plot(times, data['net_recv'], 'm-', label='Received', linewidth=1.5)
        ax.set_ylabel('Network (bytes/s)')
        ax.legend()
        ax.grid(True)
        ax.set_title(f'Network Traffic ({config["NET_INTERFACE"]})')
        plot_idx += 1

    if config.get('MONITOR_LOAD'):
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['load1'], label='1 min', linewidth=1.5)
        ax.plot(times, data['load5'], label='5 min', linewidth=1.5)
        ax.plot(times, data['load15'], label='15 min', linewidth=1.5)
        ax.set_ylabel('Load Average')
        ax.legend()
        ax.grid(True)
        ax.set_title('System Load')
        plot_idx += 1

    if config.get('MONITOR_PROCESSES'):
        ax = fig.add_subplot(gs[plot_idx])
        ax.plot(times, data['processes'], 'purple', linewidth=1.5)
        ax.set_ylabel('Process Count')
        ax.grid(True)
        ax.set_title('Total Processes')
        plot_idx += 1
    
    fig.supxlabel('Time (seconds)')
    fig.suptitle(f'Performance Monitor - {host_alias}', fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()