# ProAutomation Studio - Build and Installer Guide for Modifications

This document outlines the essential steps to rebuild the application executable and its Windows installer after any code modifications.

## Process Overview:

1.  **Modify Application Code:**
    *   Make any necessary changes to your Python source files (`.py`) within the `DEC_HMI_APP` directory.

2.  **Build Executable with PyInstaller:**
    *   **Purpose:** Convert your Python scripts and dependencies into a standalone Windows executable.
    *   **Action:** Open a terminal in the `DEC_HMI_APP` directory and run:
        ```bash
        pyinstaller main_window.spec
        ```
    *   **Result:** This creates a `dist\ProAutomationApp` folder containing your compiled application and all its assets.

3.  **Compile Installer with Inno Setup:**
    *   **Purpose:** Package the `dist\ProAutomationApp` contents into a user-friendly `setup.exe` installer.
    *   **Pre-requisite:** Ensure `dist\ProAutomationApp` exists from the previous step.
    *   **Action:**
        1.  Open the `A:\Github_Dec\DEC_HMI_APP\setup_script.iss` file using Inno Setup Compiler.
        2.  **Important:** Verify or update the `AppId` in `setup_script.iss` with a unique GUID if this is a new major release or to avoid conflicts.
        3.  Go to `Build -> Compile` within Inno Setup.
    *   **Result:** A `ProAutomation_Studio_Setup.exe` installer will be generated in the `DEC_HMI_APP\InstallerOutput` folder.

This streamlined process ensures that any changes are correctly reflected in the distributed application.