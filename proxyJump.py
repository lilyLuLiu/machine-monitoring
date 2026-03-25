import paramiko
import tempfile
import time


class SSHViaJump:
    def __init__(
        self,
        jump_host,
        jump_user,
        jump_key_path,
        remote_host,
        remote_user,
        remote_key_path_on_jump,
        retries=20,
        delay=10,
    ):
        self.jump_host = jump_host
        self.jump_user = jump_user
        self.jump_key_path = jump_key_path

        self.remote_host = remote_host
        self.remote_user = remote_user
        self.remote_key_path_on_jump = remote_key_path_on_jump

        self.retries = retries
        self.delay = delay

        self.jump_client = None
        self.remote_client = None
        self.remote_key_local = None
        self.channel = None

        self._connect()

    # -------------------------
    # internal connect
    # -------------------------
    def _connect(self):
        for i in range(self.retries):
            try:
                # 1. connect jump
                self.jump_client = paramiko.SSHClient()
                self.jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                self.jump_client.connect(
                    hostname=self.jump_host,
                    username=self.jump_user,
                    key_filename=self.jump_key_path,
                )

                # 2. fetch remote key from jump
                sftp = self.jump_client.open_sftp()

                tmp = tempfile.NamedTemporaryFile(delete=False)
                self.remote_key_local = tmp.name
                tmp.close()

                sftp.get(self.remote_key_path_on_jump, self.remote_key_local)
                sftp.close()

                # 3. create tunnel jump -> remote
                transport = self.jump_client.get_transport()

                self.channel = transport.open_channel(
                    kind="direct-tcpip",
                    dest_addr=(self.remote_host, 2222),
                    src_addr=("127.0.0.1", 0),
                )

                # 4. connect remote via tunnel
                self.remote_client = paramiko.SSHClient()
                self.remote_client.set_missing_host_key_policy(
                    paramiko.AutoAddPolicy()
                )

                self.remote_client.connect(
                    hostname=self.remote_host,
                    username=self.remote_user,
                    key_filename=self.remote_key_local,
                    sock=self.channel,
                )
                return  # Success
            except Exception as e:
                print(f"Connect failed on attempt {i + 1}: {e}")
                if i < self.retries - 1:
                    print(f"Retrying in {self.delay} seconds...")
                    time.sleep(self.delay)
                else:
                    print("All connection attempts failed.")
                    raise

    # -------------------------
    # public API: run command
    # -------------------------
    def run(self, cmd):
        stdin, stdout, stderr = self.remote_client.exec_command(cmd)
        out = stdout.read().decode()
        err = stderr.read().decode()
        return stdin, out, err

    # -------------------------
    # close everything
    # -------------------------
    def close(self):
        if self.remote_client:
            self.remote_client.close()

        if self.jump_client:
            self.jump_client.close()

        self.remote_client = None
        self.jump_client = None
        self.channel = None

"""
client = SSHViaJump(
    jump_host = "rhel-crcqe.tpb.lab.eng.brq.redhat.com",
    jump_user = "cloud-user",
    jump_key_path = "/Users/lul/Documents/code/my-qe-platform/qe-platform/config/private/hosts/rhel-1-brno-key",

    remote_host = "localhost",
    remote_user = "core",
    remote_key_path_on_jump = "/home/cloud-user/.crc/machines/crc/id_ed25519",
)

out, err = client.run("hostname && whoami")
print("OUT:", out)
print("ERR:", err)

out, err = client.run("df -h")
print(out)

client.close()
"""


class SSHDirect:
    def __init__(self, host, user, key_path, port=22, retries=5, delay=10):
        self.host = host
        self.user = user
        self.key_path = key_path
        self.port = port
        self.retries = retries
        self.delay = delay
        self.client = None
        self._connect()

    def _connect(self):
        for i in range(self.retries):
            try:
                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    key_filename=self.key_path,
                )
                return  # Success
            except Exception as e:
                print(f"Connect failed on attempt {i + 1}/{self.retries}: {e}")
                if i < self.retries - 1:
                    print(f"Retrying in {self.delay} seconds...")
                    time.sleep(self.delay)
                else:
                    print("All connection attempts failed.")
                    raise

    def run(self, cmd):
        stdin, stdout, stderr = self.client.exec_command(cmd)
        out = stdout.read().decode()
        err = stderr.read().decode()
        return stdin, out, err

    def close(self):
        if self.client:
            self.client.close()
        self.client = None


def parse_ssh_config(config_path):
    config = {}
    with open(config_path) as f:
        lines = f.readlines()
    
    host_section = None
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        parts = line.split()
        key = parts[0]
        value = ' '.join(parts[1:])
        
        if key.lower() == 'host':
            host_section = value
            config[host_section] = {}
        elif host_section:
            config[host_section][key] = value
            
    return config