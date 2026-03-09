import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
import nest_asyncio
import re
import os
import json
import threading
from queue import Queue
import logging
import webbrowser
from datetime import datetime
from PIL import Image, ImageTk  # إضافة مكتبة PIL للتعامل مع الصور

# Apply nest_asyncio
nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram Bulk Message Sender")
        self.root.geometry("1000x750")  # زيادة الارتفاع قليلاً
        
        self.colors = {
            'bg': '#ffffff',
            'primary': '#0088cc',
            'secondary': '#e7f3ff',
            'success': '#00b894',
            'warning': '#fdcb6e',
            'error': '#d63031',
            'text': '#2d3436',
            'light_text': '#636e72',
        }
        
        self.root.configure(bg=self.colors['bg'])
        
        # Variables
        self.df = None
        self.api_id = None
        self.api_hash = None
        self.phone_number = None
        self.client = None
        self.columns = []
        self.name_column = tk.StringVar()
        self.phone_column = tk.StringVar()
        self.country_code = tk.StringVar(value="90")
        self.message_template = tk.StringVar()
        self.message_template.set("Hello {name} 👋")
        
        # Image variables
        self.image_path = None
        self.image_preview = None
        
        # Queue for communication
        self.message_queue = Queue()
        self.is_running = False
        self.code_callback = None
        self.password_callback = None
        self.login_in_progress = False
        
        # Load config
        self.load_config()
        
        # Create asyncio loop
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.start_loop, args=(self.loop,), daemon=True)
        self.thread.start()
        
        self.setup_ui()
        self.check_queue()
        
    def start_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        
    def check_queue(self):
        try:
            while True:
                msg = self.message_queue.get_nowait()
                if msg['type'] == 'log':
                    self.log(msg['text'], msg.get('tag'))
                elif msg['type'] == 'progress':
                    self.progress['value'] = msg['value']
                elif msg['type'] == 'enable_send':
                    self.send_button.config(state="normal")
                elif msg['type'] == 'finished':
                    messagebox.showinfo("Complete", msg['text'])
                elif msg['type'] == 'password_request':
                    self.root.after(0, self.show_password_dialog)
                elif msg['type'] == 'code_request':
                    self.root.after(0, self.show_code_dialog)
                elif msg['type'] == 'update_login_button':
                    self.login_button.config(text=msg['text'], bg=msg['bg'])
                elif msg['type'] == 'enable_login':
                    self.login_button.config(state="normal")
                    self.login_in_progress = False
                elif msg['type'] == 'close_dialog':
                    # إغلاق أي نافذة حوار مفتوحة
                    pass
        except:
            pass
        finally:
            self.root.after(100, self.check_queue)
    
    def show_code_dialog(self):
        """نافذة إدخال الكود"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Verification Code")
        dialog.geometry("450x350")
        dialog.configure(bg=self.colors['bg'])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (dialog.winfo_screenheight() // 2) - (350 // 2)
        dialog.geometry(f'+{x}+{y}')
        
        frame = tk.Frame(dialog, bg=self.colors['bg'])
        frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        # Icon
        tk.Label(frame, text="📱", font=('Segoe UI', 48), bg=self.colors['bg']).pack(pady=(0, 10))
        
        # Title
        tk.Label(frame, text="Verification Code", 
                font=('Segoe UI', 16, 'bold'), 
                fg=self.colors['primary'],
                bg=self.colors['bg']).pack(pady=(0, 5))
        
        # Phone info
        phone_display = self.phone_entry.get()
        tk.Label(frame, text=f"Code sent to {phone_display}",
                font=('Segoe UI', 10), 
                fg=self.colors['light_text'],
                bg=self.colors['bg']).pack(pady=(0, 20))
        
        # Code entry
        code_var = tk.StringVar()
        code_entry = tk.Entry(frame, textvariable=code_var, 
                             font=('Segoe UI', 24), 
                             justify='center',
                             width=6,
                             bg='white',
                             relief='solid',
                             bd=1)
        code_entry.pack(pady=(0, 15), ipady=10)
        code_entry.focus()
        
        # Status label
        status_label = tk.Label(frame, text="", 
                               font=('Segoe UI', 10),
                               fg=self.colors['error'],
                               bg=self.colors['bg'])
        status_label.pack(pady=(0, 15))
        
        def submit_code():
            """إرسال الكود"""
            code = code_var.get().strip()
            if code and len(code) >= 4:
                # تعطيل الإدخال
                code_entry.config(state='disabled')
                status_label.config(text="⏳ Verifying code...", fg=self.colors['primary'])
                dialog.update()
                
                # إرسال الكود للتحقق
                asyncio.run_coroutine_threadsafe(
                    self.verify_code(code, dialog, status_label, code_entry), 
                    self.loop
                )
            else:
                status_label.config(text="❌ Please enter a valid code", fg=self.colors['error'])
        
        def resend_code():
            """إعادة إرسال الكود"""
            status_label.config(text="⏳ Resending code...", fg=self.colors['primary'])
            dialog.update()
            
            asyncio.run_coroutine_threadsafe(
                self.resend_code(dialog, status_label),
                self.loop
            )
        
        # Buttons frame
        btn_frame = tk.Frame(frame, bg=self.colors['bg'])
        btn_frame.pack(fill=tk.X, pady=5)
        
        # Verify button
        verify_btn = tk.Button(btn_frame, text="Verify", 
                              command=submit_code,
                              bg=self.colors['primary'], 
                              fg='white',
                              font=('Segoe UI', 11, 'bold'), 
                              relief='flat',
                              cursor='hand2',
                              padx=30, 
                              pady=8)
        verify_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        # Resend button
        resend_btn = tk.Button(btn_frame, text="Resend Code", 
                              command=resend_code,
                              bg=self.colors['secondary'], 
                              fg=self.colors['primary'],
                              font=('Segoe UI', 11, 'bold'), 
                              relief='flat',
                              cursor='hand2',
                              padx=30, 
                              pady=8)
        resend_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        # Bind Enter key
        code_entry.bind('<Return>', lambda e: submit_code())
    
    async def verify_code(self, code, dialog, status_label, code_entry):
        """التحقق من الكود"""
        try:
            self.log(f"🔑 Verifying code: {code}", 'info')
            
            # محاولة تسجيل الدخول بالكود
            await self.client.sign_in(phone=self.phone_entry.get(), code=code)
            
            # إذا نجح التسجيل
            self.log("✅ Login successful!", 'success')
            
            # تحديث الواجهة
            self.message_queue.put({'type': 'enable_send'})
            self.message_queue.put({
                'type': 'update_login_button',
                'text': "✅ Connected",
                'bg': self.colors['success']
            })
            
            # إغلاق نافذة الحوار
            self.root.after(0, dialog.destroy)
            
        except SessionPasswordNeededError:
            # مطلوب كلمة مرور للتحقق الثنائي
            self.log("🔐 Two-factor authentication required", 'info')
            self.root.after(0, dialog.destroy)
            self.root.after(500, lambda: self.message_queue.put({'type': 'password_request'}))
            
        except PhoneCodeInvalidError:
            # كود غير صحيح
            error_msg = "❌ Invalid code. Please try again."
            self.log(error_msg, 'error')
            self.root.after(0, lambda: self.show_code_error(dialog, code_entry, status_label, error_msg))
            
        except PhoneCodeExpiredError:
            # الكود انتهت صلاحيته
            error_msg = "❌ Code expired. Please request a new one."
            self.log(error_msg, 'error')
            self.root.after(0, lambda: self.show_code_error(dialog, code_entry, status_label, error_msg))
            
        except FloodWaitError as e:
            # انتظار بسبب المحاولات الكثيرة
            error_msg = f"⏳ Too many attempts. Wait {e.seconds} seconds."
            self.log(error_msg, 'warning')
            self.root.after(0, lambda: self.show_code_error(dialog, code_entry, status_label, error_msg))
            
        except Exception as e:
            # أي خطأ آخر
            error_msg = f"❌ Error: {str(e)}"
            self.log(error_msg, 'error')
            self.root.after(0, lambda: self.show_code_error(dialog, code_entry, status_label, error_msg))
    
    def show_code_error(self, dialog, code_entry, status_label, message):
        """عرض خطأ في الكود وإعادة تمكين الإدخال"""
        code_entry.config(state='normal')
        code_entry.delete(0, tk.END)
        code_entry.focus()
        status_label.config(text=message, fg=self.colors['error'])
    
    async def resend_code(self, dialog, status_label):
        """إعادة إرسال الكود"""
        try:
            # إعادة إنشاء العميل إذا لزم الأمر
            if not self.client or not self.client.is_connected():
                self.client = TelegramClient('session', int(self.api_id_entry.get()), self.api_hash_entry.get())
                await self.client.connect()
            
            # إرسال طلب كود جديد
            await self.client.send_code_request(self.phone_entry.get())
            
            self.log("📱 Code resent successfully", 'success')
            self.root.after(0, lambda: status_label.config(
                text="✅ Code sent! Check your phone", 
                fg=self.colors['success']
            ))
            
        except Exception as e:
            error_msg = f"❌ Failed to resend: {str(e)}"
            self.log(error_msg, 'error')
            self.root.after(0, lambda: status_label.config(text=error_msg, fg=self.colors['error']))
    
    def show_password_dialog(self):
        """نافذة إدخال كلمة المرور للتحقق الثنائي"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Two-Factor Authentication")
        dialog.geometry("400x300")
        dialog.configure(bg=self.colors['bg'])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (300 // 2)
        dialog.geometry(f'+{x}+{y}')
        
        frame = tk.Frame(dialog, bg=self.colors['bg'])
        frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        # Icon
        tk.Label(frame, text="🔐", font=('Segoe UI', 48), bg=self.colors['bg']).pack(pady=(0, 10))
        
        # Title
        tk.Label(frame, text="Two-Factor Authentication", 
                font=('Segoe UI', 14, 'bold'), 
                fg=self.colors['primary'],
                bg=self.colors['bg']).pack(pady=(0, 5))
        
        # Instructions
        tk.Label(frame, text="Enter your password",
                font=('Segoe UI', 10), 
                fg=self.colors['light_text'],
                bg=self.colors['bg']).pack(pady=(0, 20))
        
        # Password entry
        password_var = tk.StringVar()
        password_entry = tk.Entry(frame, textvariable=password_var, 
                                  font=('Segoe UI', 14), 
                                  show="•", 
                                  justify='center',
                                  width=15,
                                  bg='white',
                                  relief='solid',
                                  bd=1)
        password_entry.pack(pady=(0, 15), ipady=5)
        password_entry.focus()
        
        # Status label
        status_label = tk.Label(frame, text="", 
                               font=('Segoe UI', 9),
                               fg=self.colors['error'],
                               bg=self.colors['bg'])
        status_label.pack(pady=(0, 10))
        
        def submit_password():
            """إرسال كلمة المرور"""
            pwd = password_var.get().strip()
            if pwd:
                password_entry.config(state='disabled')
                status_label.config(text="⏳ Verifying...", fg=self.colors['primary'])
                dialog.update()
                
                asyncio.run_coroutine_threadsafe(
                    self.verify_password(pwd, dialog, status_label, password_entry), 
                    self.loop
                )
            else:
                status_label.config(text="❌ Please enter password", fg=self.colors['error'])
        
        # Submit button
        submit_btn = tk.Button(frame, text="Login", 
                              command=submit_password,
                              bg=self.colors['primary'], 
                              fg='white',
                              font=('Segoe UI', 11, 'bold'), 
                              relief='flat',
                              cursor='hand2',
                              padx=30, 
                              pady=8)
        submit_btn.pack()
        
        # Bind Enter
        password_entry.bind('<Return>', lambda e: submit_password())
    
    async def verify_password(self, password, dialog, status_label, password_entry):
        """التحقق من كلمة المرور"""
        try:
            await self.client.sign_in(password=password)
            
            self.log("✅ Login successful!", 'success')
            self.message_queue.put({'type': 'enable_send'})
            self.message_queue.put({
                'type': 'update_login_button',
                'text': "✅ Connected",
                'bg': self.colors['success']
            })
            
            self.root.after(0, dialog.destroy)
            
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            self.log(error_msg, 'error')
            self.root.after(0, lambda: self.show_password_error(dialog, password_entry, status_label, error_msg))
    
    def show_password_error(self, dialog, password_entry, status_label, message):
        """عرض خطأ في كلمة المرور"""
        password_entry.config(state='normal')
        password_entry.delete(0, tk.END)
        password_entry.focus()
        status_label.config(text=message, fg=self.colors['error'])
    
    def open_api_link(self):
        webbrowser.open("https://my.telegram.org/apps")
        self.log("🌐 Opened Telegram API page")
    
    def create_header(self, parent, text, icon):
        header = tk.Frame(parent, bg=self.colors['secondary'], height=35)
        header.pack(fill=tk.X, pady=(0, 10))
        header.pack_propagate(False)
        
        tk.Label(header, text=f"{icon} {text}", 
                font=('Segoe UI', 11, 'bold'), 
                bg=self.colors['secondary'],
                fg=self.colors['primary']).pack(side=tk.LEFT, padx=10, pady=7)
        
        return header
    
    def setup_ui(self):
        main = tk.Frame(self.root, bg=self.colors['bg'])
        main.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Title
        title = tk.Frame(main, bg=self.colors['bg'])
        title.pack(fill=tk.X, pady=(0, 15))
        tk.Label(title, text="📨 Telegram Bulk Sender", 
                font=('Segoe UI', 16, 'bold'),
                fg=self.colors['primary'],
                bg=self.colors['bg']).pack(side=tk.LEFT)
        
        # API Settings
        self.create_header(main, "API Configuration", "🔐")
        settings = tk.Frame(main, bg=self.colors['bg'])
        settings.pack(fill=tk.X, pady=(0, 15))
        
        # API ID
        row1 = tk.Frame(settings, bg=self.colors['bg'])
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="API ID:", width=10, anchor='w', bg=self.colors['bg']).pack(side=tk.LEFT)
        self.api_id_entry = tk.Entry(row1, width=20, bg='white', relief='solid', bd=1)
        self.api_id_entry.pack(side=tk.LEFT, padx=(0, 5))
        if self.api_id: self.api_id_entry.insert(0, self.api_id)
        tk.Button(row1, text="Get ID", command=self.open_api_link,
                 bg=self.colors['secondary'], fg=self.colors['primary'],
                 relief='flat', cursor='hand2').pack(side=tk.LEFT)
        
        # API Hash
        row2 = tk.Frame(settings, bg=self.colors['bg'])
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="API Hash:", width=10, anchor='w', bg=self.colors['bg']).pack(side=tk.LEFT)
        self.api_hash_entry = tk.Entry(row2, width=30, bg='white', relief='solid', bd=1)
        self.api_hash_entry.pack(side=tk.LEFT)
        if self.api_hash: self.api_hash_entry.insert(0, self.api_hash)
        
        # Phone
        row3 = tk.Frame(settings, bg=self.colors['bg'])
        row3.pack(fill=tk.X, pady=2)
        tk.Label(row3, text="Phone:", width=10, anchor='w', bg=self.colors['bg']).pack(side=tk.LEFT)
        self.phone_entry = tk.Entry(row3, width=20, bg='white', relief='solid', bd=1)
        self.phone_entry.pack(side=tk.LEFT)
        if self.phone_number: self.phone_entry.insert(0, self.phone_number)
        
        # Buttons
        btn_row = tk.Frame(settings, bg=self.colors['bg'])
        btn_row.pack(fill=tk.X, pady=(10, 0))
        
        tk.Button(btn_row, text="💾 Save", command=self.save_config,
                 bg=self.colors['secondary'], fg=self.colors['primary'],
                 relief='flat', cursor='hand2', padx=15, pady=5).pack(side=tk.LEFT, padx=(0, 5))
        
        self.login_button = tk.Button(btn_row, text="🔌 Connect", command=self.login_telegram,
                                      bg=self.colors['primary'], fg='white',
                                      relief='flat', cursor='hand2', padx=15, pady=5)
        self.login_button.pack(side=tk.LEFT)
        
        # Country
        self.create_header(main, "Country", "🌍")
        country = tk.Frame(main, bg=self.colors['bg'])
        country.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(country, text="Code:", bg=self.colors['bg']).pack(side=tk.LEFT, padx=(0, 5))
        self.country_combo = ttk.Combobox(country, textvariable=self.country_code, 
                                         values=["90", "966", "962", "20", "971", "974", "1", "44"],
                                         width=5)
        self.country_combo.pack(side=tk.LEFT)
        
        # Excel
        self.create_header(main, "Excel File", "📊")
        excel = tk.Frame(main, bg=self.colors['bg'])
        excel.pack(fill=tk.X, pady=(0, 15))
        
        tk.Button(excel, text="📂 Choose", command=self.load_excel,
                 bg=self.colors['secondary'], fg=self.colors['primary'],
                 relief='flat', cursor='hand2', padx=15, pady=5).pack(side=tk.LEFT, padx=(0, 10))
        
        self.file_label = tk.Label(excel, text="No file", 
                                  fg=self.colors['light_text'], bg=self.colors['bg'])
        self.file_label.pack(side=tk.LEFT)
        
        # Columns
        self.create_header(main, "Columns", "📌")
        cols = tk.Frame(main, bg=self.colors['bg'])
        cols.pack(fill=tk.X, pady=(0, 15))
        
        # Name
        name_row = tk.Frame(cols, bg=self.colors['bg'])
        name_row.pack(fill=tk.X, pady=2)
        tk.Label(name_row, text="Name Column:", width=12, anchor='w', bg=self.colors['bg']).pack(side=tk.LEFT)
        self.name_combo = ttk.Combobox(name_row, textvariable=self.name_column, state="readonly", width=25)
        self.name_combo.pack(side=tk.LEFT)
        
        # Phone
        phone_row = tk.Frame(cols, bg=self.colors['bg'])
        phone_row.pack(fill=tk.X, pady=2)
        tk.Label(phone_row, text="Phone Column:", width=12, anchor='w', bg=self.colors['bg']).pack(side=tk.LEFT)
        self.phone_combo = ttk.Combobox(phone_row, textvariable=self.phone_column, state="readonly", width=25)
        self.phone_combo.pack(side=tk.LEFT)
        
        # Image section - جديد
        self.create_header(main, "Image Attachment (Optional)", "🖼️")
        image_frame = tk.Frame(main, bg=self.colors['bg'])
        image_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Buttons for image
        image_btn_frame = tk.Frame(image_frame, bg=self.colors['bg'])
        image_btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(image_btn_frame, text="📷 Choose Image", command=self.choose_image,
                 bg=self.colors['secondary'], fg=self.colors['primary'],
                 relief='flat', cursor='hand2', padx=15, pady=5).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(image_btn_frame, text="❌ Remove Image", command=self.remove_image,
                 bg=self.colors['error'], fg='white',
                 relief='flat', cursor='hand2', padx=15, pady=5).pack(side=tk.LEFT)
        
        # Image info and preview
        self.image_label = tk.Label(image_frame, text="No image selected", 
                                   fg=self.colors['light_text'], bg=self.colors['bg'])
        self.image_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.image_preview_label = tk.Label(image_frame, bg=self.colors['bg'], relief='solid', bd=1)
        self.image_preview_label.pack(side=tk.LEFT, padx=5)
        
        # Message
        self.create_header(main, "Message", "💬")
        msg = tk.Frame(main, bg=self.colors['bg'])
        msg.pack(fill=tk.X, pady=(0, 15))
        
        text_frame = tk.Frame(msg, bg='white', relief='solid', bd=1)
        text_frame.pack(fill=tk.X)
        self.message_text = tk.Text(text_frame, height=4, font=('Segoe UI', 9),
                                    wrap=tk.WORD, bd=0, padx=5, pady=5)
        self.message_text.pack(fill=tk.BOTH, expand=True)
        self.message_text.insert('1.0', self.message_template.get())
        
        # Controls
        ctrl = tk.Frame(main, bg=self.colors['bg'])
        ctrl.pack(fill=tk.X, pady=(10, 15))
        
        self.preview_button = tk.Button(ctrl, text="👁️ Preview", 
                                       command=self.preview_messages,
                                       bg=self.colors['secondary'], fg=self.colors['primary'],
                                       relief='flat', cursor='hand2', padx=15, pady=5,
                                       state="disabled")
        self.preview_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.check_button = tk.Button(ctrl, text="🔍 Validate", 
                                     command=self.check_phone_numbers,
                                     bg=self.colors['secondary'], fg=self.colors['primary'],
                                     relief='flat', cursor='hand2', padx=15, pady=5)
        self.check_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.send_button = tk.Button(ctrl, text="🚀 Send", 
                                    command=self.send_messages,
                                    bg=self.colors['success'], fg='white',
                                    relief='flat', cursor='hand2', padx=15, pady=5,
                                    state="disabled")
        self.send_button.pack(side=tk.LEFT)
        
        # Progress
        prog = tk.Frame(main, bg=self.colors['bg'])
        prog.pack(fill=tk.X, pady=(0, 15))
        self.progress = ttk.Progressbar(prog, length=600, mode='determinate')
        self.progress.pack()
        
        # Log
        self.create_header(main, "Log", "📋")
        log_container = tk.Frame(main, bg='white', relief='solid', bd=1)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        log_frame = tk.Frame(log_container, bg='white')
        log_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        self.log_text = tk.Text(log_frame, height=6, font=('Segoe UI', 8),
                                wrap=tk.WORD, bd=0, padx=5, pady=5)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Tags
        self.log_text.tag_configure('success', foreground=self.colors['success'])
        self.log_text.tag_configure('error', foreground=self.colors['error'])
        self.log_text.tag_configure('warning', foreground=self.colors['warning'])
        self.log_text.tag_configure('info', foreground=self.colors['primary'])
    
    def choose_image(self):
        """اختيار صورة للإرفاق"""
        file_path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            try:
                # التحقق من حجم الصورة (الحد الأقصى 10 ميجابايت)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # حجم بالميجابايت
                if file_size > 10:
                    messagebox.showwarning("Warning", "Image size should be less than 10MB")
                    return
                
                self.image_path = file_path
                filename = os.path.basename(file_path)
                self.image_label.config(text=f"✅ {filename} ({file_size:.1f} MB)", 
                                      fg=self.colors['success'])
                
                # عرض صورة مصغرة
                self.show_image_preview(file_path)
                
                self.log(f"🖼️ Image selected: {filename}", 'success')
                
            except Exception as e:
                self.log(f"❌ Error loading image: {str(e)}", 'error')
                messagebox.showerror("Error", f"Failed to load image:\n{str(e)}")
    
    def show_image_preview(self, image_path):
        """عرض صورة مصغرة"""
        try:
            # فتح الصورة وتغيير حجمها
            pil_image = Image.open(image_path)
            pil_image.thumbnail((100, 100))  # تغيير الحجم إلى 100x100 كحد أقصى
            
            # تحويل إلى صورة Tkinter
            photo = ImageTk.PhotoImage(pil_image)
            
            # تحديث الملصق
            self.image_preview_label.config(image=photo)
            self.image_preview_label.image = photo  # الاحتفاظ بمرجع للصورة
            
        except Exception as e:
            self.log(f"❌ Error creating preview: {str(e)}", 'error')
    
    def remove_image(self):
        """إزالة الصورة المحددة"""
        self.image_path = None
        self.image_label.config(text="No image selected", fg=self.colors['light_text'])
        self.image_preview_label.config(image='')
        self.image_preview_label.image = None
        self.log("🖼️ Image removed", 'info')
    
    def save_config(self):
        config = {
            'api_id': self.api_id_entry.get(),
            'api_hash': self.api_hash_entry.get(),
            'phone_number': self.phone_entry.get(),
            'country_code': self.country_code.get()
        }
        try:
            with open('telegram_config.json', 'w') as f:
                json.dump(config, f)
            self.log("✅ Settings saved", 'success')
        except Exception as e:
            self.log(f"❌ Error: {str(e)}", 'error')
    
    def load_config(self):
        try:
            if os.path.exists('telegram_config.json'):
                with open('telegram_config.json', 'r') as f:
                    config = json.load(f)
                self.api_id = config.get('api_id', '')
                self.api_hash = config.get('api_hash', '')
                self.phone_number = config.get('phone_number', '')
                self.country_code.set(config.get('country_code', '90'))
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def log(self, message, tag=None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        if tag:
            self.log_text.insert(tk.END, log_entry, tag)
        else:
            self.log_text.insert(tk.END, log_entry)
        
        self.log_text.see(tk.END)
        self.root.update()
    
    def load_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            try:
                self.df = pd.read_excel(path)
                self.columns = list(self.df.columns)
                
                self.name_combo['values'] = self.columns
                self.phone_combo['values'] = self.columns
                
                # Auto-detect
                for col in self.columns:
                    col_lower = str(col).lower()
                    if any(x in col_lower for x in ['name', 'isim', 'ad', 'اسم']):
                        self.name_column.set(col)
                    if any(x in col_lower for x in ['phone', 'mobile', 'tel', 'هاتف']):
                        self.phone_column.set(col)
                
                self.file_label.config(text=f"✅ {os.path.basename(path)}", fg=self.colors['success'])
                self.preview_button.config(state="normal")
                self.log(f"📊 Loaded: {os.path.basename(path)}", 'success')
                self.log(f"📋 Records: {len(self.df)}", 'info')
                
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.log(f"❌ Error: {str(e)}", 'error')
    
    def login_telegram(self):
        if self.login_in_progress:
            return
            
        if not all([self.api_id_entry.get(), self.api_hash_entry.get(), self.phone_entry.get()]):
            messagebox.showwarning("Warning", "Enter all credentials")
            return
        
        self.login_in_progress = True
        self.log("🔄 Connecting...", 'info')
        self.login_button.config(state="disabled", text="⏳ Connecting...")
        
        asyncio.run_coroutine_threadsafe(self.login_async(), self.loop)
    
    async def login_async(self):
        try:
            # حذف الجلسة القديمة
            if os.path.exists('session.session'):
                os.remove('session.session')
                self.log("🗑️ Removed old session", 'info')
            
            # إنشاء عميل جديد
            self.client = TelegramClient('session', int(self.api_id_entry.get()), self.api_hash_entry.get())
            await self.client.connect()
            
            # التحقق من حالة التسجيل
            if await self.client.is_user_authorized():
                self.log("✅ Already connected!", 'success')
                self.message_queue.put({'type': 'enable_send'})
                self.message_queue.put({
                    'type': 'update_login_button',
                    'text': "✅ Connected",
                    'bg': self.colors['success']
                })
                self.login_in_progress = False
                return
            
            # طلب الكود
            self.log("📱 Requesting verification code...", 'info')
            await self.client.send_code_request(self.phone_entry.get())
            
            self.log("✅ Code sent! Check your phone", 'success')
            self.message_queue.put({'type': 'code_request'})
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}", 'error')
            self.message_queue.put({'type': 'update_login_button', 'text': "🔌 Connect", 'bg': self.colors['primary']})
            self.message_queue.put({'type': 'enable_login'})
            self.login_in_progress = False
    
    def preview_messages(self):
        if not self.df or not self.name_column.get() or not self.phone_column.get():
            return
        
        preview = tk.Toplevel(self.root)
        preview.title("Preview")
        preview.geometry("600x500")
        
        text = tk.Text(preview, font=('Segoe UI', 10), padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        
        template = self.message_text.get('1.0', tk.END).strip()
        
        # إضافة معلومات الصورة إذا وجدت
        if self.image_path:
            text.insert(tk.END, f"🖼️ Image: {os.path.basename(self.image_path)}\n\n", 'info')
        
        for _, row in self.df.head(5).iterrows():
            name = row[self.name_column.get()]
            phone = row[self.phone_column.get()]
            msg = template.replace("{name}", str(name)).replace("{phone}", str(phone))
            
            text.insert(tk.END, f"To: {name}\nPhone: {phone}\nMessage: {msg}\n{'-'*40}\n\n")
        
        text.config(state=tk.DISABLED)
        
        # تكوين العلامات
        text.tag_configure('info', foreground=self.colors['primary'], font=('Segoe UI', 10, 'bold'))
        
        tk.Button(preview, text="Close", command=preview.destroy).pack(pady=5)
    
    def check_phone_numbers(self):
        if not self.df or not self.phone_column.get():
            return
        
        valid = 0
        invalid = 0
        
        for _, row in self.df.iterrows():
            phone = str(row[self.phone_column.get()])
            clean = re.sub(r'\D', '', phone)
            if 10 <= len(clean) <= 15:
                valid += 1
                self.log(f"✅ {phone}", 'success')
            else:
                invalid += 1
                self.log(f"❌ {phone}", 'error')
        
        self.log(f"📊 Valid: {valid}, Invalid: {invalid}", 'info')
        messagebox.showinfo("Results", f"Valid: {valid}\nInvalid: {invalid}")
    
    async def send_message(self, phone, message, name, idx, total):
        try:
            clean = '+' + re.sub(r'\D', '', phone)
            entity = await self.client.get_input_entity(clean)
            
            # إرسال الصورة إذا وجدت
            if self.image_path and os.path.exists(self.image_path):
                await self.client.send_file(entity, self.image_path, caption=message)
                self.log(f"✅ ({idx}/{total}) Sent to {name} (with image)", 'success')
            else:
                await self.client.send_message(entity, message)
                self.log(f"✅ ({idx}/{total}) Sent to {name}", 'success')
            
            return True
        except FloodWaitError as e:
            self.log(f"⏳ ({idx}/{total}) Rate limited. Wait {e.seconds}s", 'warning')
            await asyncio.sleep(e.seconds)
            # محاولة مرة أخرى بعد الانتظار
            return await self.send_message(phone, message, name, idx, total)
        except Exception as e:
            self.log(f"❌ ({idx}/{total}) Failed: {str(e)}", 'error')
            return False
    
    async def send_all(self):
        template = self.message_text.get('1.0', tk.END).strip()
        total = len(self.df)
        success = 0
        failed = 0
        
        self.message_queue.put({'type': 'progress', 'value': 0})
        
        for idx, row in self.df.iterrows():
            name = row[self.name_column.get()]
            phone = str(row[self.phone_column.get()])
            msg = template.replace("{name}", str(name)).replace("{phone}", phone)
            
            if await self.send_message(phone, msg, name, idx+1, total):
                success += 1
            else:
                failed += 1
            
            self.message_queue.put({'type': 'progress', 'value': (idx+1) * 100 // total})
            
            # تأخير بين الرسائل لتجنب الحظر
            await asyncio.sleep(3)  # زيادة التأخير قليلاً
        
        self.log(f"📊 Complete: {success} sent, {failed} failed", 'info')
        self.message_queue.put({'type': 'finished', 'text': f"Sent {success} messages"})
        self.is_running = False
        
        # إعادة تمكين الأزرار
        self.message_queue.put({'type': 'enable_send'})
    
    def send_messages(self):
        if not self.client:
            messagebox.showwarning("Warning", "Connect to Telegram first")
            return
        
        if self.df is None:
            messagebox.showwarning("Warning", "Load Excel file first")
            return
        
        if self.is_running:
            return
        
        # تأكيد الإرسال
        msg_count = len(self.df)
        confirm_msg = f"Send {msg_count} messages"
        if self.image_path:
            confirm_msg += f"\nwith image: {os.path.basename(self.image_path)}"
        
        if messagebox.askyesno("Confirm", confirm_msg + "?"):
            self.is_running = True
            self.send_button.config(state="disabled")
            self.log("🚀 Starting...", 'info')
            asyncio.run_coroutine_threadsafe(self.send_all(), self.loop)

def main():
    root = tk.Tk()
    app = TelegramSenderApp(root)
    
    def on_closing():
        if app.loop.is_running():
            app.loop.call_soon_threadsafe(app.loop.stop)
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
