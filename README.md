# RoK Auto Alliance Bot

Automation bot for **Rise of Kingdoms** that handles repetitive daily alliance tasks through a BlueStacks Android emulator. The bot uses ADB to control the game, combining OCR (Tesseract), template matching (OpenCV), and fixed-coordinate fallbacks to detect UI elements and navigate reliably.

## Features

| Task | What it does |
|---|---|
| **1-Troop Build** | Navigates to a bookmarked alliance building marked "1 TROOP", clicks BUILD, dispatches one troop via a chosen march preset |
| **Alliance Donation** | Opens alliance technology, finds the Officer's Recommended tech (red banner detection), donates 20 times (daily cap) |
| **Expedition Collection** | Opens the campaign/expedition screen, collects reward chests and pending rewards |
| **Territory Claim** | Opens alliance territory and presses CLAIM |

### Additional Capabilities

- **Character Rotation** -- iterates through up to 22 characters on one account
- **Account Rotation** -- logs out and back in to different accounts (email/password)
- **Session Resume** -- JSON checkpoint files allow interrupted sessions to continue where they left off
- **Scheduled Automation** -- configurable intervals from 1 to 48 hours
- **Multi-Instance** -- run separate BlueStacks instances in parallel, each with independent configuration
- **Three-Tier Detection** -- template image matching -> OCR text detection -> fixed coordinates, for resilience against minor UI variations
- **Click-and-Verify Navigation** -- every action is verified by checking the resulting screen state
- **Error Recovery** -- automatic retry with escape-to-home recovery on failures

## Screenshots

*Coming soon*

## Requirements

- **Windows 10/11**
- **Python 3.10+**
- **BlueStacks Nougat 64-bit** with an instance configured at **1280x720** resolution
- **Tesseract OCR** (bundled in release builds, or [install separately](https://github.com/UB-Mannheim/tesseract/wiki))
- **Rise of Kingdoms** installed in the BlueStacks instance (Global, KR, and Gamota versions supported)

### Game Setup

- Game language must be set to **English**
- Disable **Opening Animation** in game settings
- For 1-Troop Build: officers must set the marker name to exactly `1 TROOP`, visible on the bookmark page without scrolling

## Installation

### From Release (Recommended)

1. Download the latest ZIP from [Releases](../../releases)
2. Extract to a location of your choice (e.g. `C:\Program Files\RoK Automation Tool`)
3. Run `rok_automation.exe`

### From Source

```bash
git clone https://github.com/minnyat/rok-auto-alliance-bot.git
cd rok-auto-alliance-bot

# Install dependencies
pip install -r requirements.txt

# Run
python src/main.py
```

## Setup

### 1. Create a BlueStacks Instance

1. Open BlueStacks Multi-Instance Manager
2. **+ Instance** -> Fresh Instance -> Nougat 64-bit
3. Set resolution to **1280x720** (required)
4. Create and note the **instance name** (e.g. `Nougat64_2`) from the desktop shortcut properties
5. Start the instance, install Rise of Kingdoms, log in
6. In BlueStacks instance settings -> Advanced -> Android Debug Bridge, note the **port number**
7. Close the instance

### 2. Configure the Bot

1. Launch the bot and go to **Manage Instances** -> **New Instance**
2. Fill in the instance name, BlueStacks instance ID, and ADB port
3. Select the instance, then click **Edit Config**:
   - **BlueStacks Path**: typically `C:\Program Files\BlueStacks_nxt\HD-Player.exe`
   - **ADB Path**: typically `C:\Program Files\BlueStacks_nxt\HD-Adb.exe`
   - **RoK Version**: Global, KR, or Gamota
   - **Character Count**: number of characters to automate
   - **March Preset**: the blue preset for 1-troop builds
   - **Automation Features**: check the tasks you want to enable
4. Click **Save Configuration**

### 3. Run

Click **Launch** or **Launch Selected**. Do not interact with the emulator while the bot is running.

## Account Rotation (Optional)

Add accounts to the instance's `config.ini`:

```ini
[Accounts]
accounts = farm1@example.com:password1, farm2@example.com:password2
```

The bot will log out and in to each account, running the full character automation for each one.

## Image Templates (Optional)

The bot works without templates (falls back to OCR and fixed coordinates), but adding templates improves accuracy:

```bash
python src/template_matcher.py capture <name> <x> <y> <width> <height>
```

Supported template names: `avatar_icon`, `settings_icon`, `characters_icon`, `bookmark_icon`, `alliance_icon`, `technology_icon`, `donate_button`, `campaign_icon`, `expedition_banner`, `march_button`, `expand_button`, `account_button`, `switch_account_button`

## Project Structure

```
src/
  main.py                    # Entry point
  unified_gui.py             # Tkinter GUI
  rok_game_controller.py     # Central orchestrator
  bluestacks_controller.py   # ADB interface
  build_automation.py        # 1-troop build task
  donation_automation.py     # Alliance donation task
  expedition_automation.py   # Expedition collection task
  territory_automation.py    # Territory claim task
  character_switcher.py      # Character rotation
  account_switcher.py        # Account logout/login rotation
  ocr_helper.py              # OCR operations (Tesseract)
  template_matcher.py        # OpenCV template matching
  screen_detector.py         # Game screen state detection
  navigation_helper.py       # Click-and-verify navigation
  coordinate_manager.py      # UI coordinate loader
  config_manager.py          # INI config + path auto-detection
  recovery_manager.py        # Error recovery + retry decorator
  progress_manager.py        # Session checkpoint/resume
  schedule_manager.py        # Scheduled automation intervals
  instance_manager.py        # Multi-instance management
  multi_instance_launcher.py # Thread-per-instance launcher
  automation_base.py         # Shared mixins
  timings.py                 # Named timing constants
  coordinates.json           # All UI coordinates (1280x720)
  templates/                 # Template images for matching
tests/                       # pytest test suite
build.py                     # PyInstaller build script
```

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Lint
ruff check src/ tests/

# Build executable
python build.py
```

## How It Works

```
                    +-----------------+
                    |   GUI / main.py |
                    +--------+--------+
                             |
                    +--------v--------+
                    | MultiInstance    |
                    | Launcher        |
                    +--------+--------+
                             |  (one thread per instance)
                    +--------v--------+
                    | RoKGame         |
                    | Controller      |
                    +--------+--------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +-------v------+ +-----v--------+
     | Account     |  | Character   | | Task          |
     | Switcher    |  | Switcher    | | Automations   |
     +-------------+  +-------------+ | (Build,       |
                                       |  Donate,      |
                                       |  Expedition,  |
                                       |  Territory)   |
                                       +-------+-------+
                                               |
                          +--------------------+--------------------+
                          |                    |                    |
                 +--------v------+  +---------v------+  +---------v-------+
                 | Template      |  | OCR Helper     |  | Fixed           |
                 | Matcher       |  | (Tesseract)    |  | Coordinates     |
                 | (OpenCV)      |  |                |  | (JSON)          |
                 +---------------+  +----------------+  +-----------------+
                          |                    |                    |
                          +--------------------+--------------------+
                                               |
                                    +----------v----------+
                                    | BlueStacks          |
                                    | Controller (ADB)    |
                                    +---------------------+
```

## Upgrading

1. Download and extract the new version to a new location
2. Copy the `Instances` folder from the old version to the new one
3. Delete the old version

## Supported Game Versions

| Version | Package |
|---|---|
| Global | `com.lilithgame.roc.gp` |
| Korean (KR) | `com.lilithgames.rok.kr` |
| Gamota | `com.lilithgame.roc.gp.vn` |

## License

This project is for educational and personal use only.
