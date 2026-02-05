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
IS_RUNNING = False
RECAST_DELAY = 0.1
CHECK_INTERVAL = 0.05
DEBUG_FORCE_FISH = False     # 调试：强制鱼 ID
DEBUG_FAST_DISCARD = False   # 调试：瞬间放生
DEBUG_FAST_FISH = False      # 调试：加速捕鱼 (新增)
DEBUG_FISH = 5275
RUN_MODE = "ALL"
FISH_BLACKLIST = set([*FISH_JUNK, *FISH_FISH])
FISH_WHITELIST = set([*FISH_CRATES])

CONFIG_FILE = "config.ini"
config = configparser.ConfigParser()

def save_config():
    config['SETTINGS'] = {
        'IS_RUNNING': str(IS_RUNNING),
        'RUN_MODE': RUN_MODE,
        'DEBUG_FORCE_FISH': str(DEBUG_FORCE_FISH),
        'DEBUG_FAST_DISCARD': str(DEBUG_FAST_DISCARD),
        'DEBUG_FAST_FISH': str(DEBUG_FAST_FISH),
        'DEBUG_FISH': str(DEBUG_FISH)
    }
    config['LISTS'] = {
        'WHITELIST': ",".join(map(str, FISH_WHITELIST)),
        'BLACKLIST': ",".join(map(str, FISH_BLACKLIST))
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

def load_config():
    global RUN_MODE, DEBUG_FISH, FISH_WHITELIST, FISH_BLACKLIST, IS_RUNNING, DEBUG_FORCE_FISH, DEBUG_FAST_DISCARD, DEBUG_FAST_FISH
    if not os.path.exists(CONFIG_FILE):
        save_config()
        return
    config.read(CONFIG_FILE, encoding='utf-8')
    s = config['SETTINGS'] if 'SETTINGS' in config else {}
    IS_RUNNING = config.getboolean('SETTINGS', 'IS_RUNNING', fallback=IS_RUNNING)
    RUN_MODE = config.get('SETTINGS', 'RUN_MODE', fallback=RUN_MODE)
    DEBUG_FORCE_FISH = config.getboolean('SETTINGS', 'DEBUG_FORCE_FISH', fallback=DEBUG_FORCE_FISH)
    DEBUG_FAST_DISCARD = config.getboolean('SETTINGS', 'DEBUG_FAST_DISCARD', fallback=DEBUG_FAST_DISCARD)
    DEBUG_FAST_FISH = config.getboolean('SETTINGS', 'DEBUG_FAST_FISH', fallback=DEBUG_FAST_FISH)
    DEBUG_FISH = config.getint('SETTINGS', 'DEBUG_FISH', fallback=DEBUG_FISH)
    
    if 'LISTS' in config:
        white_raw = config.get('LISTS', 'WHITELIST', fallback="")
        if white_raw: FISH_WHITELIST = set(map(int, white_raw.split(",")))
        black_raw = config.get('LISTS', 'BLACKLIST', fallback="")
        if black_raw: FISH_BLACKLIST = set(map(int, black_raw.split(",")))
    save_config()

class Stats:
    caught_count = 0
    ignored_count = 0
    fish_counts = {}      
    ignored_details = {}  
    STATUS_STOPPED = "系统已停止"
    STATUS_DISCONNECTED = "未连接游戏"
    STATUS_CONNECTED = "已连接 | 待机中"
    STATUS_FISHING = "正在自动钓鱼"
    current_status = STATUS_STOPPED
    status_color = "gray"

def get_fish_name(fid):
    return MASTER_FISH_LIST.get(fid, f"未知({fid})")

def human_click():
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.1, 0.15))
    pyautogui.mouseUp()

def get_base_by_pattern(pm):
    # 更新后的特征码：
    # 变化点：原本的 \x7a\x44\x00 变为了 \x7a\x48\x00 (对应汇编 cmp dword ptr [edx+48],00)
    pattern = b"\x55\x8b\xec\x57\x56\x53\x83\xec.\x33\xc0\x89\x45.\x8b\xd9\x83\x7a\x48\x00"
    try:
        # 搜索函数入口点
        func_start = pymem.pattern.pattern_scan_all(pm.process_handle, pattern, return_multiple=False)
        if func_start:
            # 根据你提供的 dump，目标指令 A1 (mov eax,[xxxx]) 依然在偏移 0x2C 处
            # +2C- A1 685EBD06 - mov eax,[06BD5E68]
            target_ins = func_start + 0x2C
            if pm.read_bytes(target_ins, 1) == b"\xa1":
                # 读取 A1 之后的 4 字节地址
                return pm.read_uint(target_ins + 1)
    except Exception as e:
        print(f"定位 proj 出错: {e}")
    return None

def get_myPlayer_addr(pm):
    # 特征码匹配 SelectPlayer 函数开头
    # 55 8B EC 56 83 EC 08 8B F1 8B 46 18 83 B8 1C 02 00 00 00
    pattern = b"\x55\x8b\xec\x56\x83\xec\x08\x8b\xf1\x8b\x46\x18\x83\xb8\x1c\x02\x00\x00\x00"
    
    try:
        func_start = pymem.pattern.pattern_scan_all(pm.process_handle, pattern, return_multiple=False)
        if func_start:
            # 根据汇编，myPlayer 的地址位于函数开头 + 0x1B 处的指令中
            # 指令是 89 15 [E8 6B BA 05]
            # 89 15 后面紧跟的 4 个字节就是目标地址
            target_ins = func_start + 0x1B
            if pm.read_bytes(target_ins, 2) == b"\x89\x15":
                return pm.read_uint(target_ins + 2)
    except Exception as e:
        print(f"定位 myPlayer 出错: {e}")
    return None

def start_fishing():
    global RUN_MODE, DEBUG_FISH, FISH_BLACKLIST, FISH_WHITELIST, IS_RUNNING, DEBUG_FORCE_FISH, DEBUG_FAST_DISCARD, DEBUG_FAST_FISH
    while True:
        if not IS_RUNNING:
            Stats.current_status = Stats.STATUS_STOPPED
            Stats.status_color = "gray"
            time.sleep(0.5); continue
            
        try:
            pm = pymem.Pymem("Terraria.exe")
            STATIC_PTR_ADDR = get_base_by_pattern(pm)
            if not STATIC_PTR_ADDR:
                Stats.current_status = Stats.STATUS_DISCONNECTED
                Stats.status_color = "red"
                time.sleep(2); continue
            MYPLAYER_ADDR = get_myPlayer_addr(pm)
            myPlayer = pm.read_int(MYPLAYER_ADDR)
            Stats.current_status = Stats.STATUS_CONNECTED
            Stats.status_color = "orange"
            was_bobber_active = False
            triggered_by_fish = False
            ignored_this_run = False
            
            while IS_RUNNING:
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
                            owner = pm.read_int(proj_ptr + 0x84)
                            aiStyle = pm.read_int(proj_ptr + 0x90)
                            active = pm.read_bytes(proj_ptr + 0x102, 1)[0]
                            if aiStyle == 61 and active != 0 and owner == myPlayer:
                                found_bobber_now = True
                                Stats.current_status = Stats.STATUS_FISHING
                                Stats.status_color = "#00FF00" 
                                ai_base = pm.read_uint(proj_ptr + 0x40)
                                localAI_base = pm.read_uint(proj_ptr + 0x44)
                                if ai_base == 0 or localAI_base == 0: continue
                                
                                # 调试功能：加速捕鱼
                                if DEBUG_FAST_FISH and pm.read_float(localAI_base + 0x8 + 1 * 0x4) < 660:
                                    pm.write_float(localAI_base + 0x8 + 1 * 0x4, 659.0  )

                                # 调试功能：强制生成指定鱼 ID
                                if RUN_MODE == "ALL" and DEBUG_FORCE_FISH:
                                    pm.write_float(localAI_base + 0x8 + 1 * 0x4, float(DEBUG_FISH))
                                
                                ai_1 = pm.read_float(ai_base + 0x8 + 1 * 0x4)
                                localAI_1 = int(pm.read_float(localAI_base + 0x8 + 1 * 0x4))
                                Stats.current_status = f"{Stats.STATUS_FISHING} | 监测中... | 进度: {localAI_1:.0f}"
                                
                                fish_name = get_fish_name(localAI_1)
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
                                    if DEBUG_FAST_DISCARD: 
                                        pm.write_float(ai_base + 0x8 + 1 * 0x4, -1.0)
                                    Stats.current_status = f"{Stats.STATUS_FISHING} | 放生中: {fish_name}"
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
            if IS_RUNNING:
                Stats.current_status = Stats.STATUS_DISCONNECTED
                Stats.status_color = "red"
            time.sleep(2)

class FilterWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("过滤详细设置")
        self.geometry("1400x1300") 
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

        categories = [("🗑️ 垃圾 (Junk)", FISH_JUNK), ("🐟 普通鱼类 (Common Fish)", FISH_FISH), ("🎗️ 有用物品 (Usable Item)", FISH_USABLE_ITEMS), 
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
    
    # 顶部状态与总开关
    status_container = tk.Frame(root, bg="#f0f0f0", height=50)
    status_container.pack(fill="x", side="top")
    status_led = tk.Label(status_container, text="●", font=("Arial", 14), bg="#f0f0f0")
    status_led.pack(side="left", padx=(15, 5))
    status_text = tk.Label(status_container, text="等待启动...", font=("Microsoft YaHei", 10, "bold"), bg="#f0f0f0")
    status_text.pack(side="left")

    is_running_var = tk.BooleanVar(value=IS_RUNNING)
    def toggle_master():
        global IS_RUNNING
        IS_RUNNING = is_running_var.get()
        save_config()
    ttk.Checkbutton(status_container, text="开启自动监听", variable=is_running_var, command=toggle_master).pack(side="right", padx=20)

    top_config_frame = ttk.Frame(root)
    top_config_frame.pack(fill="x", padx=10, pady=10)
    
    # 模式选择
    mode_frame = ttk.LabelFrame(top_config_frame, text="运行模式")
    mode_frame.pack(side="top", fill="x", pady=5)
    filter_btn = ttk.Button(mode_frame, text="⚙ 过滤列表设置", command=lambda: FilterWindow(root))
    filter_btn.pack(side="right", padx=10)
    mode_var = tk.StringVar(value=RUN_MODE)
    def on_mode_change(): 
        global RUN_MODE
        RUN_MODE = mode_var.get()
        filter_btn.config(state="disabled" if RUN_MODE == "ALL" else "normal")
        save_config()
    for m in [("黑名单", "BLACKLIST"), ("白名单", "WHITELIST"), ("全部捕获", "ALL")]:
        ttk.Radiobutton(mode_frame, text=m[0], variable=mode_var, value=m[1], command=on_mode_change).pack(side="left", padx=15, pady=5)

    # --- 调试功能重构为两行 ---
    debug_frame = ttk.LabelFrame(top_config_frame, text="调试功能")
    debug_frame.pack(side="top", fill="x", pady=5)

    # 第一行：加速功能
    row1 = ttk.Frame(debug_frame)
    row1.pack(fill="x", padx=10, pady=2)
    
    fast_fish_val = tk.BooleanVar(value=DEBUG_FAST_FISH)
    def toggle_fast_fish():
        global DEBUG_FAST_FISH
        DEBUG_FAST_FISH = fast_fish_val.get(); save_config()
    ttk.Checkbutton(row1, text="加速捕鱼 (瞬间咬钩)", variable=fast_fish_val, command=toggle_fast_fish).pack(side="left", padx=5)

    fast_discard_val = tk.BooleanVar(value=DEBUG_FAST_DISCARD)
    def toggle_fast_discard():
        global DEBUG_FAST_DISCARD
        DEBUG_FAST_DISCARD = fast_discard_val.get(); save_config()
    ttk.Checkbutton(row1, text="加速放生 (自动过滤)", variable=fast_discard_val, command=toggle_fast_discard).pack(side="left", padx=20)

    # 第二行：修改功能
    row2 = ttk.Frame(debug_frame)
    row2.pack(fill="x", padx=10, pady=2)
    
    force_fish_val = tk.BooleanVar(value=DEBUG_FORCE_FISH)
    def toggle_force_fish():
        global DEBUG_FORCE_FISH
        DEBUG_FORCE_FISH = force_fish_val.get(); save_config()
    ttk.Checkbutton(row2, text="强制修改鱼 ID (仅全部模式):", variable=force_fish_val, command=toggle_force_fish).pack(side="left", padx=5)
    
    fish_id_var = tk.StringVar(value=str(DEBUG_FISH))
    def on_id_change(*args):
        global DEBUG_FISH
        try:
            if fish_id_var.get(): DEBUG_FISH = int(fish_id_var.get()); save_config()
        except: pass
    fish_id_var.trace_add("write", on_id_change)
    ttk.Entry(row2, textvariable=fish_id_var, width=8).pack(side="left", padx=5)

    # 数据列表部分
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

    style = ttk.Style()
    style.configure("Treeview", rowheight=35, font=('Microsoft YaHei', 10))

    def update_ui():
        status_led.config(foreground=Stats.status_color)
        status_text.config(text=Stats.current_status)
        stat_label.config(text=f"已捕获: {Stats.caught_count} | 已放生: {Stats.ignored_count}")
        for i in tree_hit.get_children(): tree_hit.delete(i)
        for n, c in sorted(Stats.fish_counts.items(), key=lambda x: x[1], reverse=True):
            tree_hit.insert("", "end", values=(n, c))
        for i in tree_ignore.get_children(): tree_ignore.delete(i)
        for n, c in sorted(Stats.ignored_details.items(), key=lambda x: x[1], reverse=True):
            tree_ignore.insert("", "end", values=(n, c))
        root.after(200, update_ui)

    update_ui()
    root.mainloop()

if __name__ == "__main__":
    load_config()
    os.system("") 
    threading.Thread(target=start_fishing, daemon=True).start()
    run_gui()