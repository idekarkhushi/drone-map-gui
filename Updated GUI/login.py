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
import bcrypt
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

my_canvas.create_text(325, 205, text="Aeromac Dynamics",
                      font=("Good Times Rg", 26, "bold"), fill="#0c1a4e", anchor="center")
my_canvas.create_text(325, 245, text="Welcome Back",
                      font=("Times New Roman", 18, "bold"), fill="#0c1a4e", anchor="center")

LABEL_X   = 185
ENTRY_X   = 205
ENTRY_W   = 240
ROW1_Y    = 290
ROW2_Y    = 345

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

BTN_W  = 220
BTN_X  = (window_width - BTN_W) // 2

def login():
    username = usr_entry.get().strip()
    password = passwd_entry.get().strip()
    if not username or not password:
        messagebox.showerror("Error", "Please enter username and password")
        return
    try:
        conn   = sqlite3.connect("Userdata.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM User_Data WHERE Username=?", (username,))
        result = cursor.fetchone()
        conn.close()
        if result:
            stored_hash = result[3]   # Password is the 4th column
            if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
                messagebox.showinfo("Success", f"Welcome {username}")
            else:
                messagebox.showerror("Error", "Invalid Username or Password")
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

    SW, SH = 500, 540
    sx = (sub.winfo_screenwidth()  - SW) // 2
    sy = (sub.winfo_screenheight() - SH) // 2
    sub.geometry(f"{SW}x{SH}+{sx}+{sy}")

    frame = customtkinter.CTkFrame(sub, fg_color="white", corner_radius=0)
    frame.pack(fill="both", expand=True)
    frame.grid_columnconfigure((0, 1), weight=1, uniform="col")

    PAD = 18
    EW  = 200
    LF  = ("Times New Roman", 14, "bold")
    EF  = ("Times New Roman", 13)
    LC  = "#0c1a4e"

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

    lbl("First Name", 0, 0);  first_name_entry       = ent(1, 0, "Enter first name")
    lbl("Last Name",  0, 1);  last_name_entry        = ent(1, 1, "Enter last name")
    lbl("Username",   2, 0);  user_name_entry        = ent(3, 0, "Enter username")
    lbl("Password",   2, 1);  password_entry         = ent(3, 1, "Enter password", show="•")
    lbl("Confirm Password", 4, 0); confirm_password_entry = ent(5, 0, "Re-enter password", show="•")
    lbl("Email",      6, 0);  email_entry            = ent(7, 0, "Enter email id")
    lbl("Mobile No",  8, 0)

    mobile_frame = customtkinter.CTkFrame(frame, fg_color="white", bg_color="transparent")
    mobile_frame.grid(row=9, column=0, columnspan=2, padx=(PAD, 4), pady=(0, 4), sticky="w")

    # ── State for dropdown ────────────────────────────────────────────────
    selected_code_var = StringVar(value="+91")
    dropdown_open     = [False]
    dropdown_win      = [None]

    code_btn = customtkinter.CTkButton(
        mobile_frame,
        textvariable=selected_code_var,
        width=75, height=32,
        fg_color="white",
        border_width=1,
        border_color="#535ce0",
        text_color="black",
        hover_color="#e8e9ff",
        font=("Times New Roman", 12),
        corner_radius=6,
    )
    code_btn.pack(side="left", padx=(0, 6))

    mobileno_entry = customtkinter.CTkEntry(
        mobile_frame, width=170, height=32,
        text_color="black", fg_color="white",
        bg_color="transparent",
        placeholder_text="Enter mobile no",
        font=("Times New Roman", 13),
        border_color="#cccccc",
    )
    mobileno_entry.pack(side="left")

    # ── Dropdown helpers ──────────────────────────────────────────────────
    def close_dropdown():
        dropdown_open[0] = False
        if dropdown_win[0] is not None:
            try:
                # Unregister from customtkinter's scaling tracker BEFORE destroy
                # to stop the DPI after() callback firing on a dead window
                customtkinter.windows.widgets.scaling.scaling_tracker \
                    .ScalingTracker.remove_window(dropdown_win[0])
            except Exception:
                pass
            try:
                dropdown_win[0].destroy()
            except Exception:
                pass
            dropdown_win[0] = None

    def select_code(code):
        selected_code_var.set(code)
        close_dropdown()

    def open_country_dropdown():
        if dropdown_open[0]:
            close_dropdown()
            return

        dropdown_open[0] = True

        code_btn.update_idletasks()
        wx = code_btn.winfo_rootx()
        wy = code_btn.winfo_rooty() + code_btn.winfo_height() + 2

        win = Toplevel(sub)
        win.overrideredirect(True)
        win.geometry(f"280x240+{wx}+{wy}")
        win.lift()
        dropdown_win[0] = win

        local_search_var = StringVar()
        trace_id         = [None]

        search_entry = customtkinter.CTkEntry(
            win,
            textvariable=local_search_var,
            placeholder_text="Search country or code…",
            width=260, height=30,
            fg_color="white", text_color="black",
            font=("Times New Roman", 12),
            border_color="#535ce0",
        )
        search_entry.pack(padx=10, pady=(8, 4))
        search_entry.focus()

        list_frame = customtkinter.CTkScrollableFrame(
            win, width=260, height=170,
            fg_color="white",
            scrollbar_button_color="#535ce0",
        )
        list_frame.pack(padx=10, pady=(0, 8))

        def sorted_matches(filter_text):
            """
            Returns COUNTRY_CODES filtered and sorted so that:
              1. Name starts-with the query  (highest priority)
              2. Code starts-with the query  e.g. typing "+9" or "91"
              3. Name contains the query     (lowest priority)
            Within each tier, alphabetical order is preserved.
            """
            if not filter_text:
                return COUNTRY_CODES          # already sorted alphabetically

            ft = filter_text.lower().lstrip("+")
            tier1, tier2, tier3 = [], [], []

            for item in COUNTRY_CODES:
                parts        = item.split("+")
                country_name = parts[0].strip().lower()
                code_digits  = parts[1].strip() if len(parts) > 1 else ""

                if country_name.startswith(ft):
                    tier1.append(item)
                elif code_digits.startswith(ft):
                    tier2.append(item)
                elif ft in country_name or ft in code_digits:
                    tier3.append(item)

            return tier1 + tier2 + tier3

        def build_list(filter_text=""):
            try:
                children = list_frame.winfo_children()
            except Exception:
                return
            for w in children:
                try:
                    w.destroy()
                except Exception:
                    pass

            for item in sorted_matches(filter_text):
                parts        = item.split("+")
                code         = "+" + parts[1].strip()
                country_name = parts[0].strip()
                btn = customtkinter.CTkButton(
                    list_frame,
                    text=f"{country_name}  {code}",
                    anchor="w",
                    width=240, height=28,
                    fg_color="transparent",
                    text_color="black",
                    hover_color="#e8e9ff",
                    font=("Times New Roman", 12),
                    corner_radius=4,
                    command=lambda c=code: select_code(c),
                )
                btn.pack(fill="x", padx=2, pady=1)

        def on_search_change(*_):
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            build_list(local_search_var.get())

        trace_id[0] = local_search_var.trace_add("write", on_search_change)
        build_list()

        def safe_close():
            if trace_id[0] is not None:
                try:
                    local_search_var.trace_remove("write", trace_id[0])
                except Exception:
                    pass
                trace_id[0] = None
            close_dropdown()

        win.bind("<FocusOut>", lambda e: sub.after(150,
                 lambda: _check_and_close(win, safe_close)))

    def _check_and_close(win, safe_close):
        try:
            if not win.winfo_exists():
                return
            if win.focus_get() is None:
                safe_close()
        except Exception:
            safe_close()

    code_btn.configure(command=open_country_dropdown)
    first_name_entry.focus()

    # ── Validators ────────────────────────────────────────────────────────
    def is_valid_username(username):
        return len(username) >= 8 and re.match(r'^[A-Za-z0-9_]+$', username) is not None

    def is_valid_email(email):
        return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

    def is_valid_password(password):
        return (len(password) >= 8
                and re.search(r'[A-Z]', password)
                and re.search(r'[a-z]', password)
                and re.search(r'[0-9]', password)
                and re.search(r'[@$!%*?&]', password))

    # ── Submit ────────────────────────────────────────────────────────────
    def signup_check():
        fstnm      = first_name_entry.get().strip()
        lstnm      = last_name_entry.get().strip()
        usrnm      = user_name_entry.get().strip()
        pswd       = password_entry.get().strip()
        cnfpswd    = confirm_password_entry.get().strip()
        eml        = email_entry.get().strip()
        mob_number = mobileno_entry.get().strip()
        mob        = f"{selected_code_var.get()}{mob_number}"   # e.g. "+919876543210"

        if not all([fstnm, lstnm, usrnm, pswd, cnfpswd, eml, mob_number]):
            messagebox.showerror("Error", "Please fill all the fields")
            return
        if not mob_number.isdigit() or not (7 <= len(mob_number) <= 12):
            messagebox.showerror("Error", "Enter a valid mobile number (7–12 digits, no spaces)")
            return
        if fstnm == usrnm:
            messagebox.showerror("Error", "Username cannot be same as first name")
            return
        if pswd != cnfpswd:
            messagebox.showerror("Error", "Passwords do not match")
            return
        if not is_valid_password(pswd):
            messagebox.showerror("Error",
                "Password must be 8+ chars with uppercase, lowercase, digit and special char (@$!%*?&)")
            return
        if not is_valid_email(eml):
            messagebox.showerror("Error", "Enter a valid email address")
            return

        hashed_password = bcrypt.hashpw(
            pswd.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

        try:
            conn = sqlite3.connect("Userdata.db")
            conn.execute('''CREATE TABLE IF NOT EXISTS User_Data
                            (First_Name TEXT, Last_Name TEXT, Username TEXT,
                             Password TEXT, Email TEXT, Mobile_No TEXT)''')
            conn.execute('''INSERT INTO User_Data VALUES (?,?,?,?,?,?)''',
                         (fstnm, lstnm, usrnm, hashed_password, eml, mob))
            conn.commit()
            conn.close()
            messagebox.showinfo("Welcome", f"Welcome {usrnm} - Registration Successful")
            sub.destroy()
            subprocess.call(['python', 'Updated GUI\\newmain.py'])
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