import os
import threading
import uuid
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import storage
import backend_manager as bm


class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Web Server Manager")
        self.root.geometry("580x420")
        self.root.minsize(480, 320)

        storage.ensure_dirs()
        self.servers = storage.load_servers()

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=8)

        ttk.Button(toolbar, text="+  New Web Server", command=self.open_add_dialog).pack(side="left")
        ttk.Button(toolbar, text="Rename", command=self.rename_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self.refresh_list).pack(side="right")

        columns = ("name", "backend", "php", "port", "status")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", selectmode="browse")
        for col, label, width in (
            ("name", "Name", 200),
            ("backend", "Backend", 90),
            ("php", "PHP", 50),
            ("port", "Port", 70),
            ("status", "Status", 110),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.tree.bind("<Double-1>", self.open_dashboard)

        hint = ttk.Label(
            root,
            text="Tip: Double-click a web server to open its dashboard.",
            foreground="gray",
        )
        hint.pack(padx=8, pady=(0, 8), anchor="w")

        self.refresh_list()

    def refresh_list(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for s in self.servers:
            status = "● Running" if bm.is_running(s) else "○ Stopped"
            php_txt = "PHP" if s.get("php") else "-"
            self.tree.insert("", "end", iid=s["id"], values=(s["name"], s["backend"], php_txt, s["port"], status))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

    def get_selected_server(self):
        sel = self.tree.selection()
        if not sel:
            return None
        sid = sel[0]
        return next((s for s in self.servers if s["id"] == sid), None)

    def open_add_dialog(self):
        AddServerDialog(self.root, self)

    def add_server(self, server):
        self.servers.append(server)
        storage.save_servers(self.servers)
        self.refresh_list()

    def rename_selected(self):
        s = self.get_selected_server()
        if not s:
            messagebox.showinfo("Notice", "Please select a web server from the list first.")
            return
        new_name = simpledialog.askstring("Rename", "New name:", initialvalue=s["name"], parent=self.root)
        if new_name and new_name.strip():
            s["name"] = new_name.strip()
            storage.save_servers(self.servers)
            self.refresh_list()

    def delete_selected(self):
        s = self.get_selected_server()
        if not s:
            messagebox.showinfo("Notice", "Please select a web server from the list first.")
            return
        if bm.is_running(s):
            if not messagebox.askyesno("Still running", "This web server is still running. Stop and delete it anyway?"):
                return
            try:
                bm.stop_server(s, storage.BACKENDS_DIR)
            except Exception as e:
                messagebox.showwarning("Warning", f"The server could not be stopped cleanly:\n{e}")
        if messagebox.askyesno("Delete", f'"{s["name"]}" really remove it from the list?\n(The content folder will be kept.)'):
            self.servers.remove(s)
            storage.save_servers(self.servers)
            self.refresh_list()

    def open_dashboard(self, event=None):
        s = self.get_selected_server()
        if not s:
            return
        DashboardWindow(self.root, s, self)


class AddServerDialog(tk.Toplevel):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.title("New Web Server")
        self.geometry("440x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.main_window = main_window
        self.folder = None

        pad = {"padx": 10, "pady": 6}

        ttk.Label(self, text="Name:").grid(row=0, column=0, sticky="w", **pad)
        default_name = f"Webserver {len(main_window.servers) + 1}"
        self.name_var = tk.StringVar(value=default_name)
        ttk.Entry(self, textvariable=self.name_var, width=32).grid(row=0, column=1, **pad)

        ttk.Label(self, text="Folder:").grid(row=1, column=0, sticky="w", **pad)
        self.folder_var = tk.StringVar(value="(no folder selected)")
        ttk.Label(self, textvariable=self.folder_var, width=30, anchor="w").grid(row=1, column=1, sticky="w", **pad)
        ttk.Button(self, text="Select folder...", command=self.choose_folder).grid(row=2, column=1, sticky="w", padx=10)

        ttk.Label(self, text="Backend:").grid(row=3, column=0, sticky="w", **pad)
        self.backend_var = tk.StringVar(value="nginx")
        backend_combo = ttk.Combobox(self, textvariable=self.backend_var, values=["nginx", "apache"], state="readonly", width=29)
        backend_combo.grid(row=3, column=1, **pad)
        backend_combo.bind("<<ComboboxSelected>>", self.on_backend_change)

        ttk.Label(self, text="Port:").grid(row=4, column=0, sticky="w", **pad)
        self.port_var = tk.IntVar(value=bm.find_free_port())
        ttk.Entry(self, textvariable=self.port_var, width=10).grid(row=4, column=1, sticky="w", **pad)

        self.php_var = tk.BooleanVar(value=False)
        self.php_check = ttk.Checkbutton(self, text="PHP support (nginx only)", variable=self.php_var)
        self.php_check.grid(row=5, column=0, columnspan=2, sticky="w", padx=10)

        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, foreground="gray").grid(row=6, column=0, columnspan=2, **pad)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)
        self.ok_button = ttk.Button(btn_frame, text="Create", command=self.on_create)
        self.ok_button.pack(side="left", padx=6)

    def on_backend_change(self, event=None):
        if self.backend_var.get() == "apache":
            self.php_var.set(False)
            self.php_check.config(state="disabled")
        else:
            self.php_check.config(state="normal")

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select the website folder", parent=self)
        if folder:
            self.folder = folder
            self.folder_var.set(folder if len(folder) < 36 else "..." + folder[-32:])

    def on_create(self):
        if not self.folder:
            messagebox.showerror("Error", "Please select a folder first.", parent=self)
            return
        try:
            port = int(self.port_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Error", "Invalid port.", parent=self)
            return

        backend = self.backend_var.get()
        name = self.name_var.get().strip() or "Webserver"
        php = self.php_var.get() and backend == "nginx"

        self.ok_button.config(state="disabled")
        self.status_var.set("Setting up server, please wait...")

        # Apache/PHP folder-selection dialogs must run on the main thread -> handle them first
        if backend == "apache":
            apache_dir = bm.ensure_apache_available(storage.BACKENDS_DIR, self)
            if not apache_dir:
                self.ok_button.config(state="normal")
                self.status_var.set("")
                return

        php_port = None
        if php:
            php_dir = bm.ensure_php_available(storage.BACKENDS_DIR, self)
            if not php_dir:
                self.ok_button.config(state="normal")
                self.status_var.set("")
                return
            php_port = bm.find_free_port(start=port + 1000)

        def progress(msg):
            self.status_var.set(msg)

        def worker():
            try:
                if backend == "nginx":
                    bm.ensure_nginx_installed(storage.BACKENDS_DIR, progress)
                sid = str(uuid.uuid4())
                instance_dir = os.path.join(storage.INSTANCES_DIR, sid)
                server = {
                    "id": sid,
                    "name": name,
                    "folder": self.folder,
                    "backend": backend,
                    "port": port,
                    "php": php,
                    "php_port": php_port,
                    "instance_dir": instance_dir,
                }
                self.after(0, lambda: self._finish(server))
            except Exception as e:
                self.after(0, lambda: self._fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, server):
        self.main_window.add_server(server)
        self.destroy()

    def _fail(self, msg):
        self.ok_button.config(state="normal")
        self.status_var.set("")
        messagebox.showerror("Error", f"The server could not be created:\n{msg}", parent=self)


class DashboardWindow(tk.Toplevel):
    def __init__(self, parent, server, main_window):
        super().__init__(parent)
        self.server = server
        self.main_window = main_window
        self.title(server["name"])
        self.geometry("380x260")
        self.resizable(False, False)
        self.transient(parent)

        ttk.Label(self, text=server["name"], font=("Segoe UI", 14, "bold")).pack(pady=(16, 4))
        backend_txt = f'Backend: {server["backend"]}'
        if server.get("php"):
            backend_txt += " (with PHP)"
        ttk.Label(self, text=backend_txt, foreground="gray").pack()

        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(self, textvariable=self.status_var, font=("Segoe UI", 10))
        self.status_label.pack(pady=8)

        ip = bm.get_local_ip()
        self.url = f"http://{ip}:{server['port']}"
        url_label = ttk.Label(self, text=self.url, foreground="blue", cursor="hand2")
        url_label.pack(pady=4)
        url_label.bind("<Button-1>", lambda e: self.open_website())

        self.toggle_button = ttk.Button(self, text="", command=self.toggle)
        self.toggle_button.pack(pady=12, ipadx=14, ipady=4)

        btns = ttk.Frame(self)
        btns.pack(pady=6)
        ttk.Button(btns, text="Open folder", command=self.open_folder).pack(side="left", padx=6)
        ttk.Button(btns, text="Open website", command=self.open_website).pack(side="left", padx=6)

        self.refresh_status()

    def refresh_status(self):
        running = bm.is_running(self.server)
        if running:
            self.status_var.set("Running")
            self.status_label.config(foreground="green")
            self.toggle_button.config(text="Stoppen")
        else:
            self.status_var.set("Stopped")
            self.status_label.config(foreground="red")
            self.toggle_button.config(text="Starten")

    def toggle(self):
        self.toggle_button.config(state="disabled")
        going_to_start = not bm.is_running(self.server)

        def worker():
            try:
                if going_to_start:
                    bm.start_server(self.server, storage.BACKENDS_DIR)
                else:
                    bm.stop_server(self.server, storage.BACKENDS_DIR)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e), parent=self))
            self.after(0, self._after_toggle)

        threading.Thread(target=worker, daemon=True).start()

    def _after_toggle(self):
        self.toggle_button.config(state="normal")
        self.refresh_status()
        self.main_window.refresh_list()

    def open_folder(self):
        try:
            os.startfile(self.server["folder"])
        except Exception as e:
            messagebox.showerror("Error", f"The folder could not be opened:\n{e}", parent=self)

    def open_website(self):
        webbrowser.open(self.url)
