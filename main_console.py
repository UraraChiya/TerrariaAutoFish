import pymem
import pymem.pattern
import time
import pyautogui
import random
import sys
import os

# --- 配置参数 ---
RECAST_DELAY = 0.1
CHECK_INTERVAL = 0.05

# Debug 模式：加快鱼释放，ALL 模式时修改渔获
DEBUG_MODE = False
DEBUG_FISH = 5275

# 运行模式选择: "BLACKLIST" (黑名单模式) / "WHITELIST" (白名单模式) / "ALL" (全部捕获)
RUN_MODE = "ALL"

from fish import *

# 黑名单：这些 ID 不收竿
FISH_BLACKLIST = [*FISH_JUNK, *FISH_FISH]

# 白名单：只收这些 ID，其他的等待信号归零
FISH_WHITELIST = [*FISH_CRATES]


# --- 统计数据 ---
class Stats:
    caught_count = 0
    ignored_count = 0
    start_time = time.time()


class Logger:
    """带颜色的统一日志处理类 - 支持 ANSI 擦除"""

    COLORS = {
        "INFO": "\033[94m",
        "MODE": "\033[92m",
        "ACTION": "\033[93m",
        "WARN": "\033[91m",
        "ERROR": "\033[91m",
        "CYAN": "\033[96m",
        "RESET": "\033[0m",
    }

    @staticmethod
    def log(message, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        color = Logger.COLORS.get(level, Logger.COLORS["INFO"])
        reset = Logger.COLORS["RESET"]
        sys.stdout.write(f"\r\033[K[{timestamp}] [{color}{level}{reset}] {message}\n")
        sys.stdout.flush()

    @staticmethod
    def status(message):
        cyan = Logger.COLORS["CYAN"]
        reset = Logger.COLORS["RESET"]
        # 计算运行时间
        elapsed = int(time.time() - Stats.start_time)
        mins, secs = divmod(elapsed, 60)
        stat_line = f" [已捕获: {Stats.caught_count} | 已过滤: {Stats.ignored_count} | 耗时: {mins:02d}:{secs:02d}]"
        sys.stdout.write(f"\r\033[K{cyan}[实时状态]{reset} {message}{stat_line}")
        sys.stdout.flush()


def get_fish_name(fid):
    # 使用导入的 MASTER_FISH_LIST
    return MASTER_FISH_LIST.get(fid, "未知鱼类")


def human_click():
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.1, 0.15))
    pyautogui.mouseUp()


def get_base_by_pattern(pm):
    pattern = (
        b"\x55\x8b\xec\x57\x56\x53\x83\xec.\x33\xc0\x89\x45.\x8b\xd9\x83\x7a\x44\x00"
    )
    try:
        func_start = pymem.pattern.pattern_scan_all(
            pm.process_handle, pattern, return_multiple=False
        )
        if func_start:
            target_ins = func_start + 0x2C
            if pm.read_bytes(target_ins, 1) == b"\xa1":
                return pm.read_uint(target_ins + 1)
    except Exception as e:
        Logger.log(f"特征码搜索失败: {e}", "ERROR")
    return None


def start_fishing():
    try:
        pm = pymem.Pymem("Terraria.exe")
        Logger.log("成功连接到 Terraria", "INFO")
    except:
        Logger.log("错误：请先启动游戏！", "ERROR")
        return

    # 动态定位基址 (遵循不使用 hardcoded staticPtr 原则)
    STATIC_PTR_ADDR = get_base_by_pattern(pm)
    if not STATIC_PTR_ADDR:
        Logger.log("无法定位静态指针", "ERROR")
        return

    Logger.log(f"动态定位成功: {hex(STATIC_PTR_ADDR)}", "INFO")
    Logger.log(f"当前运行模式: {RUN_MODE}", "MODE")

    auto_loop_active = False
    was_bobber_active = False
    triggered_by_fish = False
    last_printed_proj = 0
    bobber_was_gone = True
    ignored_this_run = False  # 黑名单锁定标记

    Logger.log("请在游戏中手动抛出【第一竿】以启动脚本...", "INFO")

    while True:
        try:
            array_obj = pm.read_uint(STATIC_PTR_ADDR)
            if array_obj == 0:
                time.sleep(0.5)
                continue

            found_bobber_now = False

            for i in range(1000):
                proj_slot_addr = array_obj + 0x8 + (i * 4)
                proj_ptr = pm.read_uint(proj_slot_addr)

                if proj_ptr < 0x01000000:
                    continue

                try:
                    aiStyle = pm.read_int(proj_ptr + 0x90)
                    active = pm.read_bytes(proj_ptr + 0x102, 1)[0]
                    owner = pm.read_int(proj_ptr + 0x84)

                    if aiStyle == 61 and active != 0:
                        found_bobber_now = True

                        if proj_ptr != last_printed_proj and bobber_was_gone:
                            Logger.log(
                                f"捕获新鱼漂 -> 地址: [[{hex(STATIC_PTR_ADDR)}] + 0x8 + ({i} * 0x4)] = {hex(proj_ptr)} 主人：{owner}",
                                "INFO",
                            )
                            last_printed_proj = proj_ptr
                            bobber_was_gone = False

                        if not auto_loop_active:
                            auto_loop_active = True
                            Logger.log("开始自动钓鱼循环", "MODE")

                        ai_base = pm.read_uint(proj_ptr + 0x40)
                        localAI_base = pm.read_uint(proj_ptr + 0x44)
                        if ai_base == 0 or localAI_base == 0:
                            continue

                        # 获取关键信号，模拟 C# 访问数组
                        ai_0 = pm.read_float(ai_base + 0x8 + 0 * 0x4)
                        ai_1 = pm.read_float(ai_base + 0x8 + 1 * 0x4)
                        localAI_1 = int(pm.read_float(localAI_base + 0x8 + 1 * 0x4))

                        fish_name = get_fish_name(localAI_1)

                        # --- 模式判定逻辑 ---
                        is_target = True
                        if RUN_MODE == "BLACKLIST":
                            if localAI_1 in FISH_BLACKLIST:
                                is_target = False
                        elif RUN_MODE == "WHITELIST":
                            if localAI_1 not in FISH_WHITELIST:
                                is_target = False
                        elif RUN_MODE == "ALL":
                            if DEBUG_MODE:
                                pm.write_float(
                                    localAI_base + 0x8 + 1 * 0x4, float(DEBUG_FISH)
                                )
                                localAI_1 = DEBUG_FISH
                                fish_name = get_fish_name(localAI_1)

                        # 1. 检测到非目标鱼正在咬钩 (信号小于 0)
                        if not is_target and ai_1 < 0:
                            if not ignored_this_run:
                                Logger.log(
                                    f"模式[{RUN_MODE}] 过滤鱼获: {fish_name} (ID: {localAI_1})",
                                    "WARN",
                                )
                                ignored_this_run = True
                                Stats.ignored_count += 1

                            if DEBUG_MODE:
                                # DEBUG 模式下通过写内存快速重置 ai_1 信号
                                pm.write_float(ai_base + 0x8 + 1 * 0x4, -1.0)
                            else:
                                Logger.status(
                                    f"释放中: {fish_name} | 进度: {ai_1:.0f} -> 0"
                                )
                            break

                        # 2. 信号归零，且之前处于屏蔽状态，重置标记
                        if ignored_this_run and ai_1 >= 0:
                            ignored_this_run = False

                        # 3. 正常拉竿逻辑判定 (非屏蔽状态)
                        if not ignored_this_run:
                            if ai_1 < 0:
                                Logger.log(
                                    f"有效咬钩! 鱼获: {fish_name} (ID: {localAI_1})",
                                    "ACTION",
                                )
                                triggered_by_fish = True
                                Stats.caught_count += 1
                                human_click()
                                time.sleep(RECAST_DELAY)
                                break
                            else:
                                Logger.status(
                                    f"监测中... | 进度: {localAI_1:.0f}"
                                )
                        break
                except:
                    continue

            # 鱼漂状态转换处理
            if was_bobber_active and not found_bobber_now:
                bobber_was_gone = True
                ignored_this_run = False
                if triggered_by_fish:
                    Logger.log("自动重抛竿...", "ACTION")
                    time.sleep(0.8)
                    human_click()
                    triggered_by_fish = False
                else:
                    Logger.log("手动收竿或鱼漂消失，挂起脚本", "WARN")
                    auto_loop_active = False

            was_bobber_active = found_bobber_now
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            Logger.log("用户停止脚本", "INFO")
            break
        except Exception:
            continue


if __name__ == "__main__":
    start_fishing()
