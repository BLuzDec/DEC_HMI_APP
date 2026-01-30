# App icon and title bar

## Icon in the title bar

To show your own image/icon in the main window title bar and in all pop-up windows (Graph Configuration, Axis Range Settings, file dialogs, message boxes):

1. **Add an icon file** in either place:
   - This folder: `assets/app_icon.ico` or `assets/app_icon.png`
   - Or project root: `app_icon.ico`, `app_icon.png`, or `icon.ico`

2. **Supported formats**: `.ico` (recommended on Windows for taskbar too) or `.png`.

3. **Sizes**: For best results, provide a `.ico` with 16×16 and 32×32, or a square `.png` (e.g. 32×32 or 64×64). Qt will scale as needed.

The app looks for (in order): `app_icon.ico`, `app_icon.png`, `icon.ico` in the app directory and in `assets/`. The first valid file found is used for the main window and for all dialogs.

## Title bar color

On Windows, the **title bar background color** is drawn by the OS (e.g. light gray/white or your accent color). Qt does not change the native title bar color. To use a custom color you would need a frameless window and a custom-drawn title bar (more involved change). The icon and window content styling (dark theme) are under app control.
