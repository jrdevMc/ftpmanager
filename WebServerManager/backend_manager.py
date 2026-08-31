import os
import re
import socket
import subprocess
import time
import urllib.request
import zipfile
from tkinter import filedialog, messagebox

NGINX_DOWNLOAD_PAGE = "https://nginx.org/en/download.html"
NGINX_BASE = "https://nginx.org/download/"
FALLBACK_NGINX_VERSION = "1.26.2"

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def find_free_port(start=8080):
    port = start
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                port += 1
    return start


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def is_pid_running(pid):
    if not pid:
        return False
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}"],
            creationflags=NO_WINDOW,
        ).decode(errors="ignore")
        return str(pid) in output
    except Exception:
        return False


def get_pid_file(server):
    if server["backend"] == "nginx":
        return os.path.join(server["instance_dir"], "logs", "nginx.pid")
    return os.path.join(server["instance_dir"], "logs", "httpd.pid")


def is_running(server):
    pid_file = get_pid_file(server)
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    return is_pid_running(pid)


# ---------------------------------------------------------------------------
# nginx: automatic download (official Windows ZIP from nginx.org)
# ---------------------------------------------------------------------------

def _get_latest_nginx_url():
    try:
        with urllib.request.urlopen(NGINX_DOWNLOAD_PAGE, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        versions = re.findall(r"nginx-([\d.]+)\.zip", html)
        if versions:
            version = sorted(versions, key=lambda v: [int(x) for x in v.split(".")])[-1]
            return f"{NGINX_BASE}nginx-{version}.zip", version
    except Exception:
        pass
    return f"{NGINX_BASE}nginx-{FALLBACK_NGINX_VERSION}.zip", FALLBACK_NGINX_VERSION


def find_installed_nginx(backends_dir):
    if not os.path.isdir(backends_dir):
        return None
    for d in os.listdir(backends_dir):
        full = os.path.join(backends_dir, d)
        if d.startswith("nginx-") and os.path.exists(os.path.join(full, "nginx.exe")):
            return full
    return None


def ensure_nginx_installed(backends_dir, progress_cb=None):
    existing = find_installed_nginx(backends_dir)
    if existing:
        return existing

    url, version = _get_latest_nginx_url()
    zip_path = os.path.join(backends_dir, f"nginx-{version}.zip")
    if progress_cb:
        progress_cb(f"Downloading nginx {version}...")
    urllib.request.urlretrieve(url, zip_path)
    if progress_cb:
        progress_cb("Extracting nginx...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(backends_dir)
    os.remove(zip_path)
    return os.path.join(backends_dir, f"nginx-{version}")


def prepare_nginx_instance(instance_dir, nginx_dir, folder, port, php=False, php_port=None):
    conf_dir = os.path.join(instance_dir, "conf")
    logs_dir = os.path.join(instance_dir, "logs")
    temp_dir = os.path.join(instance_dir, "temp")
    for d in (conf_dir, logs_dir, temp_dir):
        os.makedirs(d, exist_ok=True)

    mime_types_path = os.path.join(nginx_dir, "conf", "mime.types").replace("\\", "/")
    fastcgi_params_path = os.path.join(nginx_dir, "conf", "fastcgi_params").replace("\\", "/")
    folder_escaped = folder.replace("\\", "/")

    index_line = "index  index.php index.html index.htm;" if php else "index  index.html index.htm;"

    php_location = ""
    if php and php_port:
        php_location = f"""
        location ~ \\.php$ {{
            fastcgi_pass 127.0.0.1:{php_port};
            fastcgi_index index.php;
            fastcgi_param SCRIPT_FILENAME "{folder_escaped}$fastcgi_script_name";
            include "{fastcgi_params_path}";
        }}
"""

    conf = f"""worker_processes  1;
error_log  logs/error.log;
pid        logs/nginx.pid;

events {{
    worker_connections  1024;
}}

http {{
    include       "{mime_types_path}";
    default_type  application/octet-stream;
    client_body_temp_path temp/client_body_temp;
    proxy_temp_path temp/proxy_temp;
    fastcgi_temp_path temp/fastcgi_temp;
    uwsgi_temp_path temp/uwsgi_temp;
    scgi_temp_path temp/scgi_temp;

    server {{
        listen       {port};
        server_name  localhost;

        location / {{
            root   "{folder_escaped}";
            {index_line}
        }}
{php_location}    }}
}}
"""
    with open(os.path.join(conf_dir, "nginx.conf"), "w", encoding="utf-8") as f:
        f.write(conf)


# ---------------------------------------------------------------------------
# PHP: no automatic download -> the user selects php-cgi.exe once.
# ---------------------------------------------------------------------------

def _php_marker_file(backends_dir):
    return os.path.join(backends_dir, "php_path.txt")


def get_saved_php_dir(backends_dir):
    marker = _php_marker_file(backends_dir)
    if os.path.exists(marker):
        with open(marker, "r", encoding="utf-8") as f:
            path = f.read().strip()
        if os.path.exists(os.path.join(path, "php-cgi.exe")):
            return path
    return None


def ensure_php_available(backends_dir, parent_window=None):
    existing = get_saved_php_dir(backends_dir)
    if existing:
        return existing

    messagebox.showinfo(
        "PHP is required",
        "There is no automatic download for PHP support.\n\n"
        "Please download PHP for Windows (the 'Non Thread Safe' "
        "CGI version is recommended) from https://windows.php.net/download/ and extract it.\n\n"
        "In the next window, select the folder containing 'php-cgi.exe'.",
        parent=parent_window,
    )
    folder = filedialog.askdirectory(title="Select PHP folder (contains php-cgi.exe)", parent=parent_window)
    if not folder:
        return None
    if not os.path.exists(os.path.join(folder, "php-cgi.exe")):
        messagebox.showerror("Error", "No php-cgi.exe was found in this folder.", parent=parent_window)
        return None

    with open(_php_marker_file(backends_dir), "w", encoding="utf-8") as f:
        f.write(folder)
    return folder


def get_php_pid_file(server):
    return os.path.join(server["instance_dir"], "logs", "php-cgi.pid")


def is_php_running(server):
    pid_file = get_php_pid_file(server)
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    return is_pid_running(pid)


def start_php_cgi(server, backends_dir):
    php_dir = get_saved_php_dir(backends_dir)
    if not php_dir:
        raise RuntimeError("PHP has not been configured yet.")
    php_cgi = os.path.join(php_dir, "php-cgi.exe")
    logs_dir = os.path.join(server["instance_dir"], "logs")
    os.makedirs(logs_dir, exist_ok=True)
    proc = subprocess.Popen(
        [php_cgi, "-b", f'127.0.0.1:{server["php_port"]}'],
        creationflags=NO_WINDOW,
    )
    with open(get_php_pid_file(server), "w", encoding="utf-8") as f:
        f.write(str(proc.pid))


def stop_php_cgi(server):
    pid_file = get_php_pid_file(server)
    if not os.path.exists(pid_file):
        return
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], creationflags=NO_WINDOW)
    except Exception:
        pass
    finally:
        try:
            os.remove(pid_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Apache: no official Windows ZIP available -> the user selects an installation
# (e.g. from apachelounge.com or an XAMPP installation) once.
# ---------------------------------------------------------------------------

def _apache_marker_file(backends_dir):
    return os.path.join(backends_dir, "apache_path.txt")


def get_saved_apache_dir(backends_dir):
    marker = _apache_marker_file(backends_dir)
    if os.path.exists(marker):
        with open(marker, "r", encoding="utf-8") as f:
            path = f.read().strip()
        if os.path.exists(os.path.join(path, "httpd.exe")):
            return path
    return None


def ensure_apache_available(backends_dir, parent_window=None):
    existing = get_saved_apache_dir(backends_dir)
    if existing:
        return existing

    messagebox.showinfo(
        "Apache is required",
        "There is no official automatic Windows download for Apache.\n\n"
        "Please download Apache manually (e.g. from apachelounge.com) and "
        "extract it somewhere on your hard drive.\n\n"
        "In the next window, select the folder containing 'httpd.exe' "
        "(usually in the 'bin' subfolder).",
        parent=parent_window,
    )
    folder = filedialog.askdirectory(
        title="Select Apache folder (contains httpd.exe or bin\\httpd.exe)",
        parent=parent_window,
    )
    if not folder:
        return None

    if os.path.exists(os.path.join(folder, "httpd.exe")):
        result = folder
    elif os.path.exists(os.path.join(folder, "bin", "httpd.exe")):
        result = os.path.join(folder, "bin")
    else:
        messagebox.showerror("Error", "No httpd.exe was found in this folder.", parent=parent_window)
        return None

    with open(_apache_marker_file(backends_dir), "w", encoding="utf-8") as f:
        f.write(result)
    return result


def prepare_apache_instance(instance_dir, apache_dir, folder, port):
    conf_dir = os.path.join(instance_dir, "conf")
    logs_dir = os.path.join(instance_dir, "logs")
    os.makedirs(conf_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    apache_dir_escaped = apache_dir.replace("\\", "/")
    folder_escaped = folder.replace("\\", "/")
    logs_escaped = logs_dir.replace("\\", "/")
    mime_types = os.path.join(apache_dir, "conf", "mime.types").replace("\\", "/")

    conf = f"""ServerRoot "{apache_dir_escaped}"
Listen {port}

LoadModule mpm_winnt_module modules/mod_mpm_winnt.so
LoadModule dir_module modules/mod_dir.so
LoadModule mime_module modules/mod_mime.so
LoadModule authz_core_module modules/mod_authz_core.so
LoadModule log_config_module modules/mod_log_config.so

TypesConfig "{mime_types}"

DocumentRoot "{folder_escaped}"
<Directory "{folder_escaped}">
    Require all granted
    DirectoryIndex index.html index.htm
</Directory>

ServerName localhost
PidFile "{logs_escaped}/httpd.pid"
ErrorLog "{logs_escaped}/error.log"
"""
    with open(os.path.join(conf_dir, "httpd.conf"), "w", encoding="utf-8") as f:
        f.write(conf)


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

def start_server(server, backends_dir):
    instance_dir = server["instance_dir"]

    if server["backend"] == "nginx":
        nginx_dir = ensure_nginx_installed(backends_dir)
        if server.get("php"):
            start_php_cgi(server, backends_dir)
        prepare_nginx_instance(
            instance_dir, nginx_dir, server["folder"], server["port"],
            php=server.get("php", False), php_port=server.get("php_port"),
        )
        nginx_exe = os.path.join(nginx_dir, "nginx.exe")
        subprocess.Popen(
            [nginx_exe, "-p", instance_dir, "-c", "conf/nginx.conf"],
            cwd=instance_dir,
            creationflags=NO_WINDOW,
        )
    else:
        apache_dir = get_saved_apache_dir(backends_dir)
        if not apache_dir:
            raise RuntimeError("Apache has not been configured yet. Please create the server again.")
        prepare_apache_instance(instance_dir, apache_dir, server["folder"], server["port"])
        httpd_exe = os.path.join(apache_dir, "httpd.exe")
        conf_path = os.path.join(instance_dir, "conf", "httpd.conf")
        subprocess.Popen(
            [httpd_exe, "-f", conf_path, "-k", "start"],
            creationflags=NO_WINDOW,
        )

    time.sleep(1)  # kurz warten, bis die PID-Datei geschrieben wurde


def stop_server(server, backends_dir):
    instance_dir = server["instance_dir"]

    if server["backend"] == "nginx":
        nginx_dir = find_installed_nginx(backends_dir)
        if nginx_dir:
            nginx_exe = os.path.join(nginx_dir, "nginx.exe")
            subprocess.run(
                [nginx_exe, "-p", instance_dir, "-s", "stop", "-c", "conf/nginx.conf"],
                cwd=instance_dir,
                creationflags=NO_WINDOW,
            )
        if server.get("php"):
            stop_php_cgi(server)
    else:
        apache_dir = get_saved_apache_dir(backends_dir)
        if apache_dir:
            httpd_exe = os.path.join(apache_dir, "httpd.exe")
            conf_path = os.path.join(instance_dir, "conf", "httpd.conf")
            subprocess.run(
                [httpd_exe, "-f", conf_path, "-k", "stop"],
                creationflags=NO_WINDOW,
            )

    time.sleep(0.5)
