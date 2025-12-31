================================================================================
                    RoK Automation Bot - User Guide
================================================================================

REQUIREMENTS
------------
1. BlueStacks 5 installed
2. Tesseract OCR installed at: C:\Program Files\Tesseract-OCR\
3. Rise of Kingdoms installed in BlueStacks

QUICK START
-----------
1. Double-click "RoK Automation.exe" to launch
2. Click "Add Instance" to create a new automation profile
3. Configure your BlueStacks instance settings
4. Select tasks to automate (Build, Donation, Expedition)
5. Click "Launch" to start automation

SETTING UP AN INSTANCE
----------------------
There are 4 fields to configure:

1. Instance Name:
   - This can be any name you want (e.g., "My Farm Account", "Main")
   - Used for display purposes only

2. BlueStacks Instance Name:
   - This is the EXACT BlueStacks instance identifier
   - To find it:
     Method A: Create a desktop shortcut for the instance in BlueStacks
              Multi-Instance Manager, right-click the shortcut > Properties,
              look at the Target field. Example:
              "C:\Program Files\BlueStacks_nxt\HD-Player.exe" --instance Nougat64_7 ...
              The instance name is: Nougat64_7

     Method B: Check BlueStacks config file at:
              %ProgramData%\BlueStacks_nxt\bluestacks.conf

3. ADB Port:
   - In BlueStacks, go to Settings > Advanced
   - Enable Android Debug Bridge (ADB)
   - Note the port number shown (e.g., 5555, 5565, 5575)
   - Each BlueStacks instance has a unique port

4. Game Version:
   - Global: Standard international version (com.lilithgame.roc.gp)
   - Gamota: Vietnamese version (com.rok.gp.vn)
   - KR: Korean version (com.lilithgames.rok.gpkr)

AUTOMATION FEATURES
-------------------
- 1 Troop Build: Dispatches 1 troop to alliance building projects
- Tech Donation: Donates to officer-recommended alliance technology
- Expedition: Collects daily expedition rewards

RUNNING MULTIPLE INSTANCES
--------------------------
1. Create separate instances for each BlueStacks emulator
2. Each instance needs a unique ADB port
3. Select multiple instances and click "Launch Selected"
4. Instances will start with a 5-second delay between each

OPTIONS
-------
- Auto-exit after done: Closes BlueStacks when automation completes
- Force daily tasks: Runs daily tasks even if already completed today
- Reset Daily Tasks: Clears the daily completion tracker

EDITING INSTANCE SETTINGS
-------------------------
1. Select an instance from the list
2. Click "Edit" to open the configuration window
3. Modify settings (characters, tasks, march preset, etc.)
4. Click "Apply Changes" to save
5. Close the window

TROUBLESHOOTING
---------------
Problem: "Tesseract not found" error
Solution: Install Tesseract OCR to C:\Program Files\Tesseract-OCR\
          Download: https://github.com/UB-Mannheim/tesseract/wiki

Problem: ADB connection fails
Solution:
  - Ensure BlueStacks is running
  - Check ADB is enabled in BlueStacks settings
  - Verify the ADB port is correct
  - Each instance must have a unique port

Problem: Automation clicks wrong locations
Solution:
  - Ensure BlueStacks resolution is 1280x720
  - Don't move or resize the BlueStacks window during automation

Problem: Bot gets stuck
Solution:
  - Click "Stop" to halt automation
  - The bot will attempt to recover automatically
  - Restart automation if needed

Problem: Multiple instances interfere with each other
Solution:
  - Each instance must have a unique ADB port
  - Don't run instances that share the same BlueStacks emulator

LOGS
----
- Console shows detailed logs during automation
- Select an instance to view its specific logs in the GUI
- Logs include OCR detection, screen state, and actions taken

TIPS
----
1. Start with one instance to verify settings work
2. Keep BlueStacks windows visible (don't minimize)
3. Disable BlueStacks notifications to avoid interruptions
4. Run automation when you won't need the computer
5. Each character should be in an alliance to use all features

================================================================================
