Portable Drive Downloader

A secure, portable, and modern GUI application for downloading Google Drive folders and files. Built with Python (PySide6) and powered by Rclone, this tool is designed to run directly from a USB stick without leaving sensitive credentials on the host machine.

🚀 Features

Portable & Self-Contained: Runs as a single executable (.exe or .app). No installation required.

Secure RAM-Only Authentication: Google Drive tokens are stored only in system RAM. If you close the app or unplug the USB, the session is wiped instantly. No rclone.conf files are left behind.

Resumable Downloads: Supports pausing and resuming downloads. If the app crashes or the internet cuts out, it picks up exactly where it left off.

Crash Protection: Download progress is auto-saved every 5 seconds.

Smart Rclone Management: Automatically downloads the correct version of Rclone for the host OS (Windows/Mac) if missing.

Modern Dark UI: Clean, responsive interface optimized for both Windows and macOS (Retina displays).

📦 How to Use

Launch the App: Double-click DriveDownloader.exe (Windows) or DriveDownloader.app (Mac).

Login: Click "Login with Google". A browser window will open. Authorize the app.

Note: Your login session exists only while the app is open.

Paste Link: Copy a Google Drive folder or file link and paste it into the input box.

Download: Click Download, select a destination folder on your computer/USB, and watch it go!

Manage: You can Pause, Resume, or Delete tasks from the list.

🛠️ Building from Source

If you want to build the binary yourself (e.g., after making code changes), follow these steps.

Prerequisites

Python 3.10+ installed.

Git installed.

1. Clone the Repository

git clone [https://github.com/YOUR_USERNAME/DriveDownloader.git](https://github.com/YOUR_USERNAME/DriveDownloader.git)
cd DriveDownloader


2. Create a Virtual Environment

It is highly recommended to use a virtual environment to keep dependencies clean.

Windows:

python -m venv venv
venv\Scripts\activate


macOS / Linux:

python3 -m venv venv
source venv/bin/activate


3. Install Dependencies

Install the required Python libraries.

pip install pyside6 requests pyinstaller


4. Build the Binary

Use PyInstaller with the included spec file to generate the executable.

pyinstaller build.spec


5. Locate the App

Once the build completes, check the dist/ folder:

Windows: dist/DriveDownloader.exe

macOS: dist/DriveDownloader.app

⚠️ Note on macOS Security

If you build on Mac or download the raw app, macOS may block it because it is not signed by Apple. To run it:

Right-click the App.

Select Open.

Click Open in the dialog box.