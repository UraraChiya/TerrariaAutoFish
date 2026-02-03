import pymem
import pymem.pattern
import time
import pyautogui
import random
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk
import configparser
from fish import *

# --- 默认配置参数 ---
RECAST_DELAY = 0.1
CHECK_INTERVAL = 0.05
DEBUG_MODE = True
DEBUG_FISH = 5275
RUN_MODE = "WHITELIST"
FISH_BLACKLIST = set([*FISH_JUNK, *FISH_FISH])
FISH_WHITELIST = set([*FISH_CRATES])

CONFIG_FILE = "config.ini"
config = configparser.ConfigParser()

def save_config():
    config['SETTINGS'] = {
        'RUN_MODE': RUN_MODE,
        'DEBUG_MODE': str(DEBUG_MODE),
        'DEBUG_FISH': str(DEBUG_FISH)
    }
    config['LISTS'] = {
        'WHITELIST': ",".join(map(str, FISH_WHITELIST)),
        'BLACKLIST': ",".join(map(str, FISH_BLACKLIST))
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

def load_config():
    global RUN_MODE, DEBUG_MODE, DEBUG_FISH, FISH_WHITELIST, FISH_BLACKLIST
    if not os.path.exists(CONFIG_FILE):
        save_config()
        return
    config.read(CONFIG_FILE, encoding='utf-8')
    if 'SETTINGS' not in config: config['SETTINGS'] = {}
    RUN_MODE = config.get('SETTINGS', 'RUN_MODE', fallback=RUN_MODE)
    DEBUG_MODE = config.getboolean('SETTINGS', 'DEBUG_MODE', fallback=DEBUG_MODE)
    DEBUG_FISH = config.getint('SETTINGS', 'DEBUG_FISH', fallback=DEBUG_FISH)
    if 'LISTS' not in config: config['LISTS'] = {}
    white_raw = config.get('LISTS', 'WHITELIST', fallback=None)
    if white_raw is not None:
        FISH_WHITELIST = set(map(int, white_raw.split(","))) if white_raw else set()
    black_raw = config.get('LISTS', 'BLACKLIST', fallback=None)
    if black_raw is not None:
        FISH_BLACKLIST = set(map(int, black_raw.split(","))) if black_raw else set()
    save_config()

class Stats:
    caught_count = 0
    ignored_count = 0
    fish_counts = {}      
    ignored_details = {}  
    STATUS_DISCONNECTED = "未连接游戏"
    STATUS_CONNECTED = "已连接 | 待机中"
    STATUS_FISHING = "正在自动钓鱼"
    current_status = STATUS_DISCONNECTED
    status_color = "gray"

class Logger:
    COLORS = {"INFO": "\033[94m", "MODE": "\033[92m", "WARN": "\033[91m", "RESET": "\033[0m"}
    @staticmethod
    def log(message, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        color = Logger.COLORS.get(level, Logger.COLORS["INFO"])
        sys.stdout.write(f"\r\033[K[{timestamp}] [{color}{level}{Logger.COLORS['RESET']}] {message}\n")
        sys.stdout.flush()

def get_fish_name(fid):
    return MASTER_FISH_LIST.get(fid, f"未知({fid})")

def human_click():
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.1, 0.15))
    pyautogui.mouseUp()

def get_base_by_pattern(pm):
    # 提醒：根据您的设置，此处特征码搜索保持动态，不使用硬编码 staticPtr
    pattern = b"\x55\x8b\xec\x57\x56\x53\x83\xec.\x33\xc0\x89\x45.\x8b\xd9\x83\x7a\x44\x00"
    try:
        func_start = pymem.pattern.pattern_scan_all(pm.process_handle, pattern, return_multiple=False)
        if func_start:
            target_ins = func_start + 0x2C
            if pm.read_bytes(target_ins, 1) == b"\xa1":
                return pm.read_uint(target_ins + 1)
    except: return None

def start_fishing():
    global RUN_MODE, DEBUG_MODE, DEBUG_FISH, FISH_BLACKLIST, FISH_WHITELIST
    while True:
        try:
            pm = pymem.Pymem("Terraria.exe")
            STATIC_PTR_ADDR = get_base_by_pattern(pm)
            if not STATIC_PTR_ADDR:
                Stats.current_status = Stats.STATUS_DISCONNECTED
                Stats.status_color = "red"
                time.sleep(2); continue
            Stats.current_status = Stats.STATUS_CONNECTED
            Stats.status_color = "orange"
            was_bobber_active = False
            triggered_by_fish = False
            ignored_this_run = False
            while True:
                try:
                    array_obj = pm.read_uint(STATIC_PTR_ADDR)
                    if array_obj == 0:
                        Stats.current_status = Stats.STATUS_CONNECTED
                        time.sleep(0.5); continue
                    found_bobber_now = False
                    for i in range(1000):
                        proj_slot_addr = array_obj + 0x8 + (i * 4)
                        proj_ptr = pm.read_uint(proj_slot_addr)
                        if proj_ptr < 0x01000000: continue
                        try:
                            aiStyle = pm.read_int(proj_ptr + 0x90)
                            active = pm.read_bytes(proj_ptr + 0x102, 1)[0]
                            if aiStyle == 61 and active != 0:
                                found_bobber_now = True
                                Stats.current_status = Stats.STATUS_FISHING
                                Stats.status_color = "#00FF00" 
                                ai_base = pm.read_uint(proj_ptr + 0x40)
                                localAI_base = pm.read_uint(proj_ptr + 0x44)
                                if ai_base == 0 or localAI_base == 0: continue
                                ai_1 = pm.read_float(ai_base + 0x8 + 1 * 0x4)
                                localAI_1 = int(pm.read_float(localAI_base + 0x8 + 1 * 0x4))
                                if RUN_MODE == "ALL" and DEBUG_MODE:
                                    pm.write_float(localAI_base + 0x8 + 1 * 0x4, float(DEBUG_FISH))
                                    localAI_1 = DEBUG_FISH
                                fish_name = get_fish_name(localAI_1)
                                Stats.current_status = f"{Stats.STATUS_FISHING} | 监测中... | 进度: {localAI_1:.0f}"
                                is_target = True
                                if RUN_MODE == "BLACKLIST":
                                    if localAI_1 in FISH_BLACKLIST: is_target = False
                                elif RUN_MODE == "WHITELIST":
                                    if localAI_1 not in FISH_WHITELIST: is_target = False
                                
                                if not is_target and ai_1 < 0:
                                    if not ignored_this_run:
                                        Stats.ignored_count += 1
                                        Stats.ignored_details[fish_name] = Stats.ignored_details.get(fish_name, 0) + 1
                                        ignored_this_run = True
                                    if DEBUG_MODE: pm.write_float(ai_base + 0x8 + 1 * 0x4, -1.0)
                                    Stats.current_status = f"{Stats.STATUS_FISHING} | 放生中: {fish_name} | 进度: {ai_1:.0f} -> 0"
                                    break
                                if ignored_this_run and ai_1 >= 0: ignored_this_run = False
                                if not ignored_this_run and ai_1 < 0:
                                    triggered_by_fish = True
                                    Stats.current_status = f"{Stats.STATUS_FISHING} | 捕捉到：{fish_name}"
                                    Stats.caught_count += 1
                                    Stats.fish_counts[fish_name] = Stats.fish_counts.get(fish_name, 0) + 1
                                    human_click()
                                    time.sleep(RECAST_DELAY); break
                                break
                        except: continue
                    if not was_bobber_active and not found_bobber_now:
                        Stats.current_status = Stats.STATUS_CONNECTED
                        Stats.status_color = "orange"
                    if was_bobber_active and not found_bobber_now:
                        ignored_this_run = False
                        if triggered_by_fish:
                            time.sleep(0.8); human_click()
                            triggered_by_fish = False
                    was_bobber_active = found_bobber_now
                    time.sleep(CHECK_INTERVAL)
                except: break
        except:
            Stats.current_status = Stats.STATUS_DISCONNECTED
            Stats.status_color = "red"
            time.sleep(2)

class FilterWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("过滤详细设置")
        self.geometry("1400x1080") 
        self.attributes("-topmost", True)
        self.transient(parent)
        self.grab_set()
        self.target_list = FISH_WHITELIST if RUN_MODE == "WHITELIST" else FISH_BLACKLIST
        self.vars = {} 
        self.setup_ui()

    def setup_ui(self):
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", padx=10, pady=5)
        header = f"编辑: {'【白名单】' if RUN_MODE == 'WHITELIST' else '【黑名单】'} - 自动保存"
        ttk.Label(top_bar, text=header, foreground="blue", font=("Microsoft YaHei", 12, "bold")).pack(side="left")

        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=5)
        scrollbar.pack(side="right", fill="y")

        categories = [("🗑️ 垃圾 (Junk)", FISH_JUNK), ("🐟 普通鱼类 (Common Fish)", FISH_FISH), 
                      ("📦 宝匣 (Crates)", FISH_CRATES), ("📜 任务鱼 (Quest)", FISH_QUEST)]
        for cat_name, cat_dict in categories:
            self.render_category(cat_name, cat_dict)

    def render_category(self, name, fish_dict):
        group_container = ttk.Frame(self.scroll_frame)
        group_container.pack(fill="x", padx=10, pady=5)
        group = ttk.LabelFrame(group_container, text=f" {name} ")
        group.pack(fill="x", expand=True)
        btn_bar = ttk.Frame(group)
        btn_bar.pack(fill="x", padx=5)
        
        def select_all(state):
            for fid in fish_dict.keys(): self.vars[fid].set(state)
            self.save_logic()

        ttk.Button(btn_bar, text="全选", width=8, command=lambda: select_all(True)).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="全不选", width=8, command=lambda: select_all(False)).pack(side="left", padx=2)
        items_container = ttk.Frame(group)
        items_container.pack(fill="both", expand=True, padx=5, pady=5)
        column_count = 8 
        for idx, (fid, fname) in enumerate(fish_dict.items()):
            var = tk.BooleanVar(value=fid in self.target_list)
            self.vars[fid] = var
            cb = ttk.Checkbutton(items_container, text=fname, variable=var, command=self.save_logic)
            cb.grid(row=idx//column_count, column=idx%column_count, sticky="w", padx=10, pady=2)

    def save_logic(self):
        global FISH_BLACKLIST, FISH_WHITELIST
        new_set = {fid for fid, var in self.vars.items() if var.get()}
        if RUN_MODE == "WHITELIST": FISH_WHITELIST = new_set
        else: FISH_BLACKLIST = new_set
        save_config()

def run_gui():
    root = tk.Tk()
    root.title("Terraria 自动钓鱼助手")
    root.geometry("750x900")
    root.attributes("-topmost", True)
    
    status_container = tk.Frame(root, bg="#f0f0f0", height=40)
    status_container.pack(fill="x", side="top")
    status_container.pack_propagate(False)
    status_led = tk.Label(status_container, text="●", font=("Arial", 14), bg="#f0f0f0")
    status_led.pack(side="left", padx=(15, 5))
    status_text = tk.Label(status_container, text="检测中...", font=("Microsoft YaHei", 10, "bold"), bg="#f0f0f0")
    status_text.pack(side="left")

    style = ttk.Style()
    style.configure("Treeview", rowheight=35, font=('Microsoft YaHei', 10))
    style.configure("Treeview.Heading", font=('Microsoft YaHei', 10, 'bold'))

    top_config_frame = ttk.Frame(root)
    top_config_frame.pack(fill="x", padx=10, pady=10)
    mode_frame = ttk.LabelFrame(top_config_frame, text="运行模式与详细配置")
    mode_frame.pack(side="top", fill="x", pady=5)

    # 声明按钮变量，以便在函数中控制其状态
    filter_btn = ttk.Button(mode_frame, text="⚙ 过滤列表设置", command=lambda: FilterWindow(root))
    filter_btn.pack(side="right", padx=10)

    mode_var = tk.StringVar(value=RUN_MODE)
    def on_mode_change(): 
        global RUN_MODE
        RUN_MODE = mode_var.get()
        # --- 新增逻辑：如果是 ALL 模式，禁用过滤按钮 ---
        if RUN_MODE == "ALL":
            filter_btn.config(state="disabled")
        else:
            filter_btn.config(state="normal")
        
        Logger.log(f"模式切换至: {RUN_MODE}", "MODE")
        save_config()

    for m in [("黑名单", "BLACKLIST"), ("白名单", "WHITELIST"), ("全部捕获", "ALL")]:
        ttk.Radiobutton(mode_frame, text=m[0], variable=mode_var, value=m[1], command=on_mode_change).pack(side="left", padx=15, pady=5)

    # 初始化时检查一次按钮状态
    if RUN_MODE == "ALL":
        filter_btn.config(state="disabled")

    debug_frame = ttk.LabelFrame(top_config_frame, text="调试模式: 将加速放生")
    debug_frame.pack(side="top", fill="x", pady=5)
    debug_val = tk.BooleanVar(value=DEBUG_MODE)
    def toggle_debug():
        global DEBUG_MODE
        DEBUG_MODE = debug_val.get()
        save_config()
    
    ttk.Checkbutton(debug_frame, text="调试模式", variable=debug_val, command=toggle_debug).pack(side="left", padx=10, pady=5)
    ttk.Label(debug_frame, text="强制生成鱼ID (仅 ALL 模式有效):").pack(side="left", padx=(20, 5))
    
    fish_id_var = tk.StringVar(value=str(DEBUG_FISH))
    def on_id_change(*args):
        global DEBUG_FISH
        try:
            v = fish_id_var.get()
            if v: 
                DEBUG_FISH = int(v)
                save_config()
        except: pass
    fish_id_var.trace_add("write", on_id_change)
    ttk.Entry(debug_frame, textvariable=fish_id_var, width=10).pack(side="left", pady=5)

    stat_label = ttk.Label(root, text="准备中...", font=("Microsoft YaHei", 11, "bold"))
    stat_label.pack(pady=10)

    paned = ttk.PanedWindow(root, orient="horizontal")
    paned.pack(fill="both", expand=True, padx=10, pady=5)

    f1 = ttk.LabelFrame(paned, text="收获清单")
    tree_hit = ttk.Treeview(f1, columns=("n", "c"), show="headings")
    tree_hit.heading("n", text="物品名"); tree_hit.heading("c", text="数量")
    tree_hit.column("n", width=140, anchor="w"); tree_hit.column("c", width=60, anchor="center")
    tree_hit.pack(fill="both", expand=True)
    paned.add(f1, weight=1)

    f2 = ttk.LabelFrame(paned, text="放生清单")
    tree_ignore = ttk.Treeview(f2, columns=("n", "c"), show="headings")
    tree_ignore.heading("n", text="物品名"); tree_ignore.heading("c", text="数量")
    tree_ignore.column("n", width=140, anchor="w"); tree_ignore.column("c", width=60, anchor="center")
    tree_ignore.pack(fill="both", expand=True)
    paned.add(f2, weight=1)

    def update_ui():
        status_led.config(foreground=Stats.status_color)
        status_text.config(text=Stats.current_status)
        stat_label.config(text=f"已捕获: {Stats.caught_count} | 已放生: {Stats.ignored_count} | 模式: {RUN_MODE}")
        for i in tree_hit.get_children(): tree_hit.delete(i)
        for n, c in sorted(Stats.fish_counts.items(), key=lambda x: x[1], reverse=True):
            tree_hit.insert("", "end", values=(n, c))
        for i in tree_ignore.get_children(): tree_ignore.delete(i)
        for n, c in sorted(Stats.ignored_details.items(), key=lambda x: x[1], reverse=True):
            tree_ignore.insert("", "end", values=(n, c))
        root.after(100, update_ui)

    update_ui()
    root.mainloop()

if __name__ == "__main__":
    load_config()
    os.system("") 
    threading.Thread(target=start_fishing, daemon=True).start()
    run_gui()