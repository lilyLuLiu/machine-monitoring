import time
from proxyJump import SSHViaJump, SSHDirect, LocalShell, parse_ssh_config

def setup_client(MONITOR_REMOTE, MONITOR_REMOTE_VM, ssh_config_path="sshConfig"):
    """Sets up the client for monitoring (remote or local)."""
    if MONITOR_REMOTE:
        ssh_config = parse_ssh_config(ssh_config_path)
        remote_config = ssh_config.get('remote', {})
        if MONITOR_REMOTE_VM:
            vm_config = ssh_config.get('vm', {})
            client = SSHViaJump(
                jump_host=remote_config.get('HostName'),
                jump_user=remote_config.get('User'),
                jump_key_path=remote_config.get('IdentityFile'),
                remote_host=vm_config.get('HostName'),
                remote_user=vm_config.get('User'),
                remote_key_path_on_jump=vm_config.get('IdentityFile'),
            )
            HOST_ALIAS = "VM in " + remote_config.get('HostName')
        else:
            client = SSHDirect(
                host=remote_config.get('HostName'),
                user=remote_config.get('User'),
                key_path=remote_config.get('IdentityFile'),
            )
            HOST_ALIAS = remote_config.get('HostName', 'RemoteHost')
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
