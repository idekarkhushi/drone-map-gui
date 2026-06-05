from tkinter import *
from tkinter import messagebox
from PIL import ImageTk, Image
import customtkinter
from customtkinter import *
import subprocess
import sqlite3
import ctypes
import os
import re
import phonenumbers
import pycountry
from phonenumbers import phonenumberutil

customtkinter.set_appearance_mode("light")
def get_all_country_codes():
    codes = []
    for country in pycountry.countries:
        try:
            phone_code = phonenumberutil.country_code_for_region(country.alpha_2)
            if phone_code:
                codes.append(f"{country.name}  +{phone_code}")
        except Exception:
            pass
    return sorted(codes)

COUNTRY_CODES = get_all_country_codes()   # built once, reused every time signup opens

main = customtkinter.CTk()
main.title("Aeromac Dynamics")
main.iconbitmap(r"Updated GUI\assets\Aeromac.ico")

main.resizable(False, False)
window_width = 650
window_height = 560
screen_width = main.winfo_screenwidth()
screen_height = main.winfo_screenheight()
x = (screen_width - window_width) // 2
y = (screen_height - window_height) // 2
main.geometry(f"{window_width}x{window_height}+{x}+{y}")

my_canvas = CTkCanvas(main, height=window_height, width=window_width)
my_canvas.pack(fill="both", expand=True)

logo_path = r"Updated GUI\assets\AD_logo.png"
logo_img = Image.open(logo_path)
resize_logo = logo_img.resize((180, 180))
logo_img_tk_img = ImageTk.PhotoImage(resize_logo)
my_canvas.create_image(235, 10, anchor="nw", image=logo_img_tk_img)

font_path = r"Updated GUI\assets\good times rg.ttf"
ctypes.windll.gdi32.AddFontResourceW(font_path)

# ── Centered title & subtitle ──────────────────────────────────────────────
my_canvas.create_text(325, 205, text="Aeromac Dynamics",
                      font=("Good Times Rg", 26, "bold"), fill="#0c1a4e", anchor="center")
my_canvas.create_text(325, 245, text="Welcome Back",
                      font=("Times New Roman", 18, "bold"), fill="#0c1a4e", anchor="center")

# ── Row layout constants ───────────────────────────────────────────────────
LABEL_X   = 185          # right-edge of label column  (anchor="e")
ENTRY_X   = 205          # left-edge of entry widget
ENTRY_W   = 240
ROW1_Y    = 290          # Username row  (label centre & entry top)
ROW2_Y    = 345          # Password row

# Labels — anchored to the right so they sit flush against the entries
my_canvas.create_text(LABEL_X, ROW1_Y + 10, text="Username",
                      font=("Times New Roman", 16), fill="#0c1a4e", anchor="e")
my_canvas.create_text(LABEL_X, ROW2_Y + 10, text="Password",
                      font=("Times New Roman", 16), fill="#0c1a4e", anchor="e")

usr_entry = customtkinter.CTkEntry(main, width=ENTRY_W, text_color="black",
                                   fg_color="white", bg_color=main.cget("fg_color"))
usr_entry.place(x=ENTRY_X, y=ROW1_Y)

passwd_entry = customtkinter.CTkEntry(main, width=ENTRY_W, text_color="black",
                                      fg_color="white", bg_color=main.cget("fg_color"), show="•")
passwd_entry.place(x=ENTRY_X, y=ROW2_Y)
usr_entry.focus()

# ── Buttons ────────────────────────────────────────────────────────────────
BTN_W  = 220
BTN_X  = (window_width - BTN_W) // 2      # horizontally centred

def login():
    username = usr_entry.get().strip()
    password = passwd_entry.get().strip()
    if not username or not password:
        messagebox.showerror("Error", "Please enter username and password")
        return
    try:
        conn   = sqlite3.connect(r"D:\Tk projects\Userdata.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM User_Data WHERE Username=? AND Password=?",
                       (username, password))
        result = cursor.fetchone()
        conn.close()
        if result:
            messagebox.showinfo("Success", f"Welcome {username}")
            subprocess.call(['python', 'anytest.py'])
        else:
            messagebox.showerror("Error", "Invalid Username or Password")
    except Exception as e:
        messagebox.showerror("Database Error", str(e))

def clear():
    usr_entry.delete(0, 'end')
    passwd_entry.delete(0, 'end')
    usr_entry.focus() 

clr_btn = customtkinter.CTkButton(main, text="Clear", height=35, width=BTN_W,
                                  fg_color="#535ce0", command=clear,
                                  text_color="white", bg_color=main.cget("fg_color"),
                                  font=("Times New Roman", 16), corner_radius=10)
clr_btn.place(x=BTN_X, y=400)

login_btn = customtkinter.CTkButton(main, text="Login", height=35, width=BTN_W,
                                    fg_color="#535ce0", command=login,
                                    text_color="white", bg_color=main.cget("fg_color"),
                                    font=("Times New Roman", 16), corner_radius=10)
login_btn.place(x=BTN_X, y=448)

signup_btn = customtkinter.CTkButton(main, text="Sign Up", height=35, width=BTN_W,
                                     fg_color="#535ce0", text_color="white",
                                     bg_color=main.cget("fg_color"),
                                     font=("Times New Roman", 16), corner_radius=10)
signup_btn.place(x=BTN_X, y=496)

# ══════════════════════════════════════════════════════════════════════════
#  SIGN-UP WINDOW
# ══════════════════════════════════════════════════════════════════════════
def signup():
    sub = customtkinter.CTk()
    sub.title("Register")
    sub.iconbitmap(r"Updated GUI\assets\Aeromac.ico")
    sub.resizable(False, False)

    SW, SH = 520, 580
    sx = (sub.winfo_screenwidth()  - SW) // 2
    sy = (sub.winfo_screenheight() - SH) // 2
    sub.geometry(f"{SW}x{SH}+{sx}+{sy}")

    # ── Grid layout inside a plain Frame ──────────────────────────────────
    frame = customtkinter.CTkFrame(sub, fg_color="white", corner_radius=0)
    frame.pack(fill="both", expand=True)
    frame.grid_columnconfigure((0, 1), weight=1, uniform="col")

    PAD   = 18   # horizontal padding inside each column
    EW    = 200  # entry width
    LF    = ("Times New Roman", 14, "bold")
    EF    = ("Times New Roman", 13)
    LC    = "#0c1a4e"

    def lbl(text, row, col, colspan=1):
        l = customtkinter.CTkLabel(frame, text=text, font=LF,
                                   text_color=LC, anchor="w")
        l.grid(row=row, column=col, columnspan=colspan,
               padx=(PAD, 4), pady=(18, 2), sticky="w")

    def ent(row, col, placeholder, show=""):
        kw = dict(width=EW, text_color="black", fg_color="white",
                  bg_color="transparent", placeholder_text=placeholder,
                  font=EF, border_color="#cccccc")
        if show:
            kw["show"] = show
        e = customtkinter.CTkEntry(frame, **kw)
        e.grid(row=row, column=col, padx=(PAD, 4), pady=(0, 4), sticky="w")
        return e

    # Row 0 – First / Last name
    lbl("First Name",        0, 0);  first_name_entry      = ent(1, 0, "Enter first name")
    lbl("Last Name",         0, 1);  last_name_entry       = ent(1, 1, "Enter last name")

    # Row 2 – Username / Password
    lbl("Username",          2, 0);  user_name_entry       = ent(3, 0, "Enter username")
    lbl("Password",          2, 1);  password_entry        = ent(3, 1, "Enter password", show="•")

    # Row 4 – Confirm password (spans both columns)
    lbl("Confirm Password",  4, 0);  confirm_password_entry = ent(5, 0, "Re-enter password")

    # Row 6 – Email (spans both columns)
    lbl("Email",             6, 0);  email_entry           = ent(7, 0, "Enter email id")

    # Row 8 – Mobile No (spans both columns)
    lbl("Mobile No",         8, 0);  # ── Mobile number row with country code dropdown ───────────────────────
    mobile_frame = customtkinter.CTkFrame(frame, fg_color="white", bg_color="transparent")
    mobile_frame.grid(row=9, column=0, columnspan=2, padx=(PAD, 4), pady=(0, 4), sticky="w")

    country_var = customtkinter.StringVar(value="India  +91")

    country_combobox = customtkinter.CTkComboBox(
        mobile_frame,
        variable=country_var,
        values=COUNTRY_CODES,
        width=80,
        height=32,
        fg_color="white",
        border_color="#535ce0",
        button_color="#535ce0",
        button_hover_color="#3a42c4",
        text_color="black",
        font=("Times New Roman", 12),
        dropdown_font=("Times New Roman", 12),
        dropdown_fg_color="white",
        dropdown_text_color="black",
        dropdown_hover_color="#e8e9ff",
        corner_radius=6,
    )
    country_combobox.pack(side="left", padx=(0, 6))
    
    mobileno_entry = customtkinter.CTkEntry(
        mobile_frame,
        width=170,
        height=32,
        text_color="black",
        fg_color="white",
        bg_color="transparent",
        placeholder_text="Enter mobile no",
        font=("Times New Roman", 13),
        border_color="#cccccc",
    )
    mobileno_entry.pack(side="left")

    first_name_entry.focus()
    
    def is_valid_username(username):
        return len(username) >= 8 and re.match(r'^[A-Za-z0-9_]+$', username) is not None
    
    def is_valid_email(email):
        pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        return re.match(pattern, email) is not None
    
    def is_valid_mobile(mobile):
        pattern = r'^\d{10}$'
        return re.match(pattern, mobile) is not None
    
    def is_valid_password(password):
        if len(password) < 8:
            return False
        if not re.search(r'[A-Z]', password):
            return False
        if not re.search(r'[a-z]', password):
            return False
        if not re.search(r'[0-9]', password):
            return False
        if not re.search(r'[@$!%*?&]', password):
            return False
        return True
    
    # ── Submit ─────────────────────────────────────────────────────────────
    def signup_check():
        pswd   = password_entry.get().strip()
        cnfpswd = confirm_password_entry.get().strip()
        usrnm  = user_name_entry.get().strip()
        fstnm  = first_name_entry.get().strip()
        lstnm  = last_name_entry.get().strip()
        eml    = email_entry.get().strip()
        mob_number = mobileno_entry.get().strip()
        selected   = country_combobox.get()             # "India  +91"
        code       = selected.split("+")[1].strip()     # "91"
        mob        = f"+{code}{mob_number}"             # "+919876543210"
        
        if not all([fstnm, lstnm, usrnm, pswd, cnfpswd, eml, mob_number]):
            messagebox.showerror("Error", "Please fill all the fields")
            return
        # Mobile number: digits only, 7–12 digits
        if not mob_number.isdigit() or not (7 <= len(mob_number) <= 12):
            messagebox.showerror("Error", "Enter a valid mobile number (7–12 digits, no spaces)")
            return
        if fstnm == usrnm:
            messagebox.showerror("Error", "Username cannot be same as first name")
            return
        if pswd != cnfpswd:
            messagebox.showerror("Error", "Passwords do not match")
            return

        try:
            conn = sqlite3.connect(r"D:\Tk projects\Userdata.db")
            conn.execute('''CREATE TABLE IF NOT EXISTS User_Data
                            (First_Name TEXT, Last_Name TEXT, Username TEXT,
                             Password TEXT, Confirm_Password TEXT,
                             Email TEXT, Mobile_No INT)''')
            conn.execute('''INSERT INTO User_Data VALUES (?,?,?,?,?,?,?)''',
                         (fstnm, lstnm, usrnm, pswd, cnfpswd, eml, mob))
            conn.commit()
            conn.close()
            messagebox.showinfo("Welcome", f"Welcome {usrnm} - Registration Successful")
            sub.destroy()
            subprocess.call(['python', 'anytest.py'])
        except Exception as e:
            messagebox.showerror("Database Error", str(e))

    submit_btn = customtkinter.CTkButton(
        frame, text="Submit", height=35, width=200,
        fg_color="#535ce0", text_color="white",
        command=signup_check, font=("Times New Roman", 15), corner_radius=10)
    submit_btn.grid(row=10, column=0, columnspan=2, pady=(20, 10))

    sub.mainloop()

signup_btn.configure(command=signup)
main.mainloop()