<p align="center"><img src="../src/train_tracker/web/img/moon-pi-logo.png" alt="Project Moon Pi" width="140"></p>

# US Train Tracker: Installation Guide

**Designed and Created by Project Moon Pi**

This guide takes you from nothing to a live train map on your computer, phone or tablet. It covers macOS,
Windows and a Raspberry Pi, and how to open the map on an iPhone or Android phone. No programming is needed.

## 1. How it works

US Train Tracker has two parts:

1. **The server**: a small program that runs on a computer (a Mac, a Windows PC or a Raspberry Pi). It
   collects live train positions, predictions and alerts from Amtrak and the commuter railroads every 20–60
   seconds, along with each railroad's schedule and the federal rail map.
2. **The map**: a web page the server provides. You open it in a web browser on the same computer, or on any
   phone, tablet or computer on the same Wi-Fi. Trains move on the map as the server receives new positions.

```
  Amtrak, MBTA, LIRR, Metro-North,       ┌──────────────────────────┐      Web browser on
  SEPTA, MARC, VRE, RTD, CapMetro …  ──► │  Server (your Mac, PC    │ ──►  the same computer,
  (live feeds, schedules, alerts)        │  or Raspberry Pi)        │      or a phone or tablet
  FRA rail map (track)               ──► │  port 7500               │      on the same Wi-Fi
                                         └──────────────────────────┘
```

Phones can't run the server themselves: the server is a Python program, and iPhones and Android phones
can't run it as an app. A phone shows the map from a server running on a computer at home. For a map
that's always available, run the server on a Raspberry Pi that stays on (section 6).

Nothing is sent anywhere except requests to the railroads' public data feeds. There's no account, and the
map is only visible on your own network unless you set up remote access (section 7).

## 2. What you need

| | Requirement |
|---|---|
| **Computer for the server** | A Mac (macOS 11 Big Sur or newer), a Windows 10 or 11 PC, a Linux computer, or a Raspberry Pi 4 or 5 (a Pi 3B+ works, more slowly) |
| **Python** | Version 3.10 or newer, from [python.org](https://www.python.org/downloads/). 3.12 or newer is recommended: 3.10 stopped getting security fixes in October 2026 |
| **Memory** | About 150–200 MB while running |
| **Disk space** | About 200 MB: the app (~40 MB) and its downloaded maps and schedules (~140 MB) |
| **Internet** | Always on while the server runs. The first start downloads about 140 MB; after that it uses about 130 MB an hour (about 3 GB a day if left running all day) |
| **To view the map** | A current web browser: Safari, Chrome, Edge or Firefox. Phones and tablets: iPhone or iPad with iOS 15 or newer, or Android with current Chrome |
| **Phones and tablets** | Must be on the same Wi-Fi as the server (or connected through remote access, section 7) |

The server is light: it sits at almost no CPU between updates. It runs in the background as a service, with
**Start** and **Stop** icons to control it; while it's stopped, the map doesn't update.

## 3. Install on a Mac

### Step 1: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/) and click **Download Python 3.x** (the
   newest version).
2. Open the downloaded `.pkg` file and click through the installer.

You only do this once. If Python is already installed, skip this step: the installer checks for it.

### Step 2: Download US Train Tracker

1. Go to the [Releases page](https://github.com/ricsne2010/train-tracker/releases/latest).
2. Under **Assets**, click **Source code (zip)**.
3. Open the downloaded zip (Safari usually unzips it for you). You get a folder named like
   `train-tracker-0.3.0`.

### Step 3: Run the installer

1. In that folder, double-click **Install Train Tracker.command**.
2. macOS may say it can't verify the developer, because the installer isn't from the App Store. To allow it:
   open **System Settings → Privacy & Security**, scroll down to the message about "Install Train
   Tracker.command", and click **Open Anyway**. (On macOS 14 or older you can instead Control-click the
   file, choose **Open**, then **Open** again.)
3. A Terminal window opens and the installer asks two questions:
   - **Phones too, or this Mac only?** Choose **Phones too** if you'll open the map on a phone or tablet.
   - **Start by itself when you log in?** Choose **Yes** to have it always running while you're logged in.
4. It installs (about a minute), starts Train Tracker, and opens the map in your browser. The very first start
   downloads the rail map and schedules, so trains can take another minute or two to appear.
5. When it says it's done, you can close the Terminal window and delete the downloaded folder.

### Start and stop

Train Tracker runs quietly in the background: there's no window to keep open. Two icons control it, on your
**Desktop** and in **Applications › Train Tracker**:

- **Start Train Tracker** (green ▶): starts it if it isn't running, and opens the map.
- **Stop Train Tracker** (red ■): shuts it down. The map stops updating until you start it again.

If you chose **Phones too** and macOS asks whether Python may accept incoming network connections, click
**Allow**. Then see section 5.

## 4. Install on Windows

### Step 1: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/) and click **Download Python 3.x**.
2. Run the installer. **On the first screen, tick "Add python.exe to PATH"**, then click **Install Now**.

### Step 2: Download US Train Tracker

1. Go to the [Releases page](https://github.com/ricsne2010/train-tracker/releases/latest).
2. Under **Assets**, click **Source code (zip)**.
3. In your Downloads folder, right-click the zip and choose **Extract All…**. You get a folder named like
   `train-tracker-0.3.0`.

### Step 3: Run the installer

1. In that folder, double-click **Install Train Tracker.bat**.
2. Windows may show "Windows protected your PC" because the installer isn't signed. Click **More info**, then
   **Run anyway**.
3. The installer asks two questions:
   - **Should phones and tablets be able to open the map?** Choose **Yes** if you'll use a phone or tablet.
   - **Start by itself when you sign in?** Choose **Yes** to have it always running while you're signed in.
4. It installs (about a minute), starts Train Tracker, and opens the map in your browser. The very first start
   downloads the rail map and schedules, so trains can take another minute or two to appear.
5. Press a key to close the installer window. You can delete the downloaded folder now.

### Start and stop

Train Tracker runs quietly in the background, with no window. Two shortcuts control it, on your **Desktop**
and in the **Start menu › Train Tracker**:

- **Start Train Tracker** (green ▶): starts it if it isn't running, and opens the map.
- **Stop Train Tracker** (red ■): shuts it down.

If you chose phones, Windows Defender Firewall asks about Python the first time it starts: allow it on
**Private networks** (your home Wi-Fi). Your Wi-Fi must be set as a private network: Settings → Network &
Internet → Wi-Fi → your network → **Private network**. Then see section 5.

## 5. Use it on an iPhone, iPad or Android phone

1. Install with **Phones too** (sections 3 and 4; run the installer again to change your answer), or use a
   Raspberry Pi (section 6), and start Train Tracker.
2. On the computer, open the map and look at the bottom of the panel for **Open on your phone**. It shows
   the address to use, such as `http://192.168.1.20:7500`, and a QR code.
3. On the phone, connected to the **same Wi-Fi**, scan the QR code with the camera, or type the address into
   Safari or Chrome.

The map fits small screens: the panel sits along the bottom; tap ☰ to fold it away.

### Put it on your home screen

- **iPhone or iPad (Safari):** tap the **Share** button, then **Add to Home Screen**, then **Add**. The
  Train Tracker icon opens the map full screen, like an app.
- **Android (Chrome):** tap **⋮**, then **Add to Home screen**. The icon opens the map in Chrome. (A full
  "installed app" window needs a secure https address, such as the remote access in section 7.)

When you're away from your Wi-Fi the icon can't reach the server, unless you've set up section 7.

## 6. Always on: a Raspberry Pi at home

A Raspberry Pi is a small, quiet, low-power computer that can run the server all the time, so the map is
always ready on your phones and computers.

**You need:** a Raspberry Pi 4 or 5 (2 GB or more), its power supply, a microSD card (16 GB or more), and
your home Wi-Fi or a network cable.

### Step 1: Set up the Pi

1. On your computer, install **Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Choose your Pi model and **Raspberry Pi OS (64-bit)** (the Lite version is enough), and your microSD card.
3. When it offers to edit settings, set a **hostname** (`raspberrypi` is fine), a **username and password**,
   your **Wi-Fi**, and turn on **SSH**. Write the card.
4. Put the card in the Pi and power it on. After a couple of minutes, open Terminal (Mac) or PowerShell
   (Windows) and connect: `ssh yourusername@raspberrypi.local`

### Step 2: Install US Train Tracker

Type these on the Pi, one line at a time. Replace `0.3.0` with the newest version on the
[Releases page](https://github.com/ricsne2010/train-tracker/releases/latest).

```
sudo apt update && sudo apt install -y python3-venv
python3 -m venv ~/train-tracker
~/train-tracker/bin/pip install https://github.com/ricsne2010/train-tracker/releases/download/v0.3.0/train_tracker-0.3.0-py3-none-any.whl
~/train-tracker/bin/train-tracker --host 0.0.0.0
```

Wait for the line *On a phone or tablet on this network, open http://…*, then open
**http://raspberrypi.local:7500** on your phone or computer. If that works, press **Ctrl+C** on the Pi to
stop it, and continue.

### Step 3: Start it automatically at power-on

```
curl -LO https://raw.githubusercontent.com/ricsne2010/train-tracker/main/tools/train-tracker@.service
sudo cp train-tracker@.service /etc/systemd/system/
sudo systemctl enable --now train-tracker@$USER
```

The map is now at **http://raspberrypi.local:7500** whenever the Pi is on. Check on it with
`systemctl status train-tracker@$USER`, and see its messages with `journalctl -u train-tracker@$USER -f`.

**To update** the Pi later: run the `pip install` line again with the new version, adding `--upgrade`, then
`sudo systemctl restart train-tracker@$USER`.

**API keys on a Pi:** the API keys page only accepts changes from the server's own computer. Either type
keys into `~/.train-tracker/.env` on the Pi (see `.env.example` in the project), or add
`--allow-remote-settings` to the `ExecStart` line of the service file to manage them from your phone.

## 7. Seeing it away from home

The simplest safe way is **Tailscale**, a free private network between your own devices:

1. Install Tailscale on the server (Mac, PC or Pi) and on your phone from [tailscale.com](https://tailscale.com/download),
   and sign in on both with the same account.
2. On the phone, open `http://<the server's Tailscale name>:7500`, for example `http://raspberrypi:7500`.

Please **don't** open port 7500 on your router to the whole internet. The map has no password, and it isn't
built to face the open internet.

## 8. API keys (optional)

Amtrak, MBTA, LIRR, Metro-North, SEPTA, MARC, VRE, RTD Denver and CapMetro work with no setup. Metra,
Caltrain, Metrolink and NJ Transit hand out free developer keys. On the map, open the panel and click **API
keys…**: each railroad has a **Get a key** link, a **Test** button and a **Save** button. Saved keys start
that railroad straight away.

## 9. Updating and removing

**Updating (Mac or Windows):** download the new **Source code (zip)** and run its installer, just like the
first time. It stops Train Tracker, updates it, and keeps your settings, API keys and downloaded data.
Running the installer again is also how you change your answers (phones, start at log-in).

**Removing:**

- **Mac:** open **Applications › Train Tracker › Uninstall Train Tracker**.
- **Windows:** **Start menu › Train Tracker › Uninstall Train Tracker**.

It removes the service, the icons and the program, then asks whether to delete your data too: the
downloaded maps and schedules, and any API keys you saved. That data lives in `~/.train-tracker` (Mac and
Raspberry Pi) or `C:\Users\<your name>\.train-tracker` (Windows).

## 10. Troubleshooting

| What you see | What to do |
|---|---|
| "Needs Python 3.10 or newer" | Install Python from python.org (step 1). On Windows, reinstall and tick **Add python.exe to PATH** |
| "Train Tracker didn't start" | Its messages say why: on a Mac in `~/Library/Logs/Train Tracker.log`, on Windows in `%LOCALAPPDATA%\TrainTracker\train-tracker.log`. A common cause is another program using port 7500 |
| Stop says it's still running | Another program is serving on port 7500 (perhaps a copy started by hand). Close it, or restart the computer |
| The browser didn't open | Open **http://127.0.0.1:7500** yourself |
| The phone can't open the address | Check the phone is on the same Wi-Fi (not mobile data or a guest network); that you installed with **Phones too**; and that you allowed Python through the firewall. Some routers keep devices apart ("client isolation" or "AP isolation"): turn that off for your home network |
| `raspberrypi.local` doesn't work | Use the Pi's numbered address instead: run `hostname -I` on the Pi |
| Map shows but no track | The first start is still downloading the rail map: wait a minute and reload |
| A railroad shows a red or amber dot | Its feed is down or its key was refused: the panel says why. Feeds come back by themselves |
| VRE shows 0 trains | Normal outside weekday rush hours |
| Metra, Caltrain, Metrolink or NJ Transit say "needs an API key" | See section 8 |

Still stuck? Open an issue on the [GitHub page](https://github.com/ricsne2010/train-tracker/issues).

---

US Train Tracker is free software (MIT licence). Train data comes from each railroad's public feeds under
their terms; see the Credits in the [README](../README.md). Built with Claude Code (Anthropic).
**Designed and Created by Project Moon Pi.**
