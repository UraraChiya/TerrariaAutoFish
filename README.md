# Terraria Auto-Fisher

[简体中文](./README_zh.md) | **English**

An advanced, memory-pattern based automated fishing assistant for Terraria. Features intelligent filtering, real-time statistics, and a modern GUI.

---

## ✨ Features

* **Smart Filtering**: 
    * **Whitelist Mode**: Only catch items you want.
    * **Blacklist Mode**: Skip specific junk/fish.
    * **Catch-All Mode**: Record everything that bites.
* **Enhanced Filter Window**:
    * Items categorized by **Junk, Common Fish, Crates, and Quest Fish**.
    * **Select/Deselect All** buttons for each category for rapid setup.
* **Adaptive UI**: 
    * The "Filter Settings" button automatically **disables** in "Catch-All" mode to prevent logical conflicts.
* **Auto-Persistence**: All settings, including lists and modes, are saved to `config.ini` in real-time.
* **Robust Memory Scanning**: Uses dynamic pattern matching to find game pointers—no hardcoded addresses required.

---

## 🚀 Usage

> [!IMPORTANT]
> The script starts automatically after the line is cast. Please keep the cursor position still; the program will simulate mouse clicks automatically.

### GUI Mode (Recommended)
```sh
uv run main.py

```

### Console Mode (Logic Only)

```sh
uv run main_console.py

```

**Note:** Console mode operates independently and does **not** read `config.ini`. Please modify the source code variables to adjust filters and modes.

---

## 📸 Screenshots

| Main Dashboard | Detailed Filter |
| --- | --- |
| <img src="./image/main.png" height="300" alt="Main UI" /> | <img src="./image/filter.png" height="300" alt="Filter UI" /> |

---

## 🛠️ Info

* **Game Version**: Tested on **Terraria 1.4.5.3** (Single Player and Dedicated Server).
* **Privileges**: Please run with **Administrator rights** to allow memory access.
* **Environment**: Python 3.13+ (Dependencies managed by `uv`).

---

## ⚙️ Configuration

The program generates a `config.ini` file on its first run. You can either use the GUI to manage your lists or manually edit the file.
