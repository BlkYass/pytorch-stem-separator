#!/usr/bin/env python3
import os, sys, threading, subprocess, shlex, tempfile, pathlib, platform
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- Defaults that matched what works for you ---
MODEL = "htdemucs_ft"
FLAGS = ["--two-stems=vocals", "-n", MODEL, "--shifts", "0", "--overlap", "0.05", "--jobs", "1", "--mp3"]

def open_in_file_manager(path: str):
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Open Folder", f"Could not open folder:\n{e}")

def locate_output_dir(out_root: str, model_name: str, audio_path: str) -> str | None:
    base = pathlib.Path(audio_path).stem
    expected = os.path.join(out_root, model_name, base)
    if os.path.isdir(expected):
        return expected
    # fallback: search
    for r, dirs, _ in os.walk(out_root):
        if os.path.basename(r) == base:
            return r
    return None

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vocal Separator (Demucs)")
        self.geometry("720x420")
        self.resizable(True, True)

        p = ttk.Frame(self, padding=10)
        p.pack(fill="both", expand=True)

        # File chooser
        row = ttk.Frame(p); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Audio file (.mp3/.wav/.m4a):").pack(side="left")
        self.inp_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.inp_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=self.pick_file).pack(side="left")

        # Output folder
        row2 = ttk.Frame(p); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="Output folder (optional):").pack(side="left")
        self.out_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row2, text="Choose…", command=self.pick_out).pack(side="left")

        # Controls
        row3 = ttk.Frame(p); row3.pack(fill="x", pady=8)
        self.run_btn = ttk.Button(row3, text="Separate (Vocals + Instrumental)", command=self.start_separation)
        self.run_btn.pack(side="left")
        ttk.Button(row3, text="Open Output Folder", command=self.open_output).pack(side="left", padx=8)

        # Log
        ttk.Label(p, text="Logs:").pack(anchor="w")
        self.log = tk.Text(p, height=12, wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        # Result
        self.result_dir = None

    def append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")
        self.update_idletasks()

    def pick_file(self):
        path = filedialog.askopenfilename(
            title="Pick audio file",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.flac"), ("All files", "*.*")]
        )
        if path:
            self.inp_var.set(path)

    def pick_out(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_var.set(path)

    def open_output(self):
        if self.result_dir and os.path.isdir(self.result_dir):
            open_in_file_manager(self.result_dir)
        else:
            messagebox.showinfo("Output", "No output yet. Run a separation first.")

    def start_separation(self):
        audio = self.inp_var.get().strip()
        if not audio or not os.path.exists(audio):
            messagebox.showerror("Input", "Please choose an existing audio file.")
            return

        out_root = self.out_var.get().strip() or os.path.join(str(pathlib.Path.home()), "separated")
        os.makedirs(out_root, exist_ok=True)

        # Build command using your working flags
        cmd = ["demucs", *FLAGS, "--out", out_root, audio]

        self.append_log(f"$ {' '.join(shlex.quote(c) for c in cmd)}\n")
        self.run_btn.configure(state="disabled")

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
                )
                for line in proc.stdout:  # stream logs to GUI
                    self.append_log(line)
                code = proc.wait()
                if code != 0:
                    raise RuntimeError(f"Demucs exited with code {code}")
                # Locate output dir and show result
                out_dir = locate_output_dir(out_root, MODEL, audio)
                self.result_dir = out_dir
                if out_dir and os.path.isdir(out_dir):
                    vocals = None
                    instrumental = None
                    for fn in os.listdir(out_dir):
                        low = fn.lower()
                        if "vocals" in low and not low.startswith("no_"):
                            vocals = os.path.join(out_dir, fn)
                        if "no_vocals" in low or "accompaniment" in low or "other" in low:
                            instrumental = os.path.join(out_dir, fn)
                    self.append_log("\n=== Done ===\n")
                    if vocals:
                        self.append_log(f"Vocals:       {vocals}\n")
                    if instrumental:
                        self.append_log(f"Instrumental: {instrumental}\n")
                    if out_dir:
                        self.append_log(f"Folder:       {out_dir}\n")
                else:
                    self.append_log("\nCould not find output folder.\n")
                self.append_log("\nTip: Click 'Open Output Folder' to view your files.\n")
            except Exception as e:
                self.append_log(f"\n[ERROR] {e}\n")
                messagebox.showerror("Separation failed", str(e))
            finally:
                self.run_btn.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    App().mainloop()

