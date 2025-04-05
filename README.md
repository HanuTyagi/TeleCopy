# 📦 TeleCopy - Telegram Message Copier & Archiver

![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)
![Status](https://img.shields.io/badge/status-active-brightgreen.svg)


```
 _________  _______   ___       _______   ________  ________  ________  ___    ___ 
|\___   ___\\  ___ \ |\  \     |\  ___ \ |\   ____\|\   __  \|\   __  \|\  \  /  /|
\|___ \  \_\ \   __/|\ \  \    \ \   __/|\ \  \___|\ \  \|\  \ \  \|\  \ \  \/  / /
     \ \  \ \ \  \_|/_\ \  \    \ \  \_|/_\ \  \    \ \  \\\  \ \   ____\ \    / / 
      \ \  \ \ \  \_|\ \ \  \____\ \  \_|\ \ \  \____\ \  \\\  \ \  \___|\/  /  /  
       \ \__\ \ \_______\ \_______\ \_______\ \_______\ \_______\ \__\ __/  / /    
        \|__|  \|_______|\|_______|\|_______|\|_______|\|_______|\|__||\___/ /     
                                                                      \|___|/      
                                                                                   By HanuTyagi
```                                                                                                         



## 🔧 Features

- 📤 Copy **Past Messages** from One Telegram chat to Another
- 📅 **Custom Date-Range** filtering for selective cloning
- 🔄 **Live Forwarding** of messages as they Arrive
- ⚙️ Interactive **Menu System** for Configuration and Actions
- 📁 Supports all media types and polls
- 💾 Automatically tracks Copied messages to avoid Duplicates
- 🧼 Resets session when API ID / Phone changes


---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/HanuTyagi/TeleCopy.git
cd TeleCopy
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
```

### 3. Activate Virtual Environment
```bash
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Start TeleCopy
```bash
python main.py
```

### 6. Set Environment Variables
``` Simply run the script and it will prompt for missing values interactively.```

---

### Note
For ```TeleCopy``` to work, You'll need an ```API_ID``` and ```API_HASH```.

You can get your own ```API_ID``` and ```API_HASH``` on this [Link](https://my.telegram.org/auth?to=apps)

Simply Login with your ```Telegram``` number, and then chose an app name of your chose and a URL.

Also, When using ```TeleCopy```, Make sure that you enter the Phone number with your countries' Phone code

---
#### 🔎 Restarting Instructions
Each time you restart the Terminal, you'll need to first activate the Virtual Environment and only then can you run ```TeleCopy```
```bash
source .venv/bin/activate
python main.py
```
---
### 🔥 Main Options
```
0. Connect to Telegram
1. Select source and destination
2. Copy Past Messages (Full Clone)
3. Start live monitoring (Auto-Forward)
4. Custom Clone (by date)
5. Update API ID, Hash, Phone
6. Exit
```
---
### 🚧 Limitation
Currently, TeleCopy can only run on Linux based Operating Systems because of

```module 'signal' has no attribute 'SIGQUIT'```

This error is because Windows Operating System currently doesn't support the library

### 🛠️ Workaround
Use ```WSL``` (Windows Subsystem for Linux) to run ```TeleCopy``` on Windows.

You can ```Google```, How to setup ```WSL``` on Windows.

Once ```WSL``` is set up, you can follow the exact setup steps listed above.

### ⛔ Error
```ImportError: libssl.so.1.1: cannot open shared object file: No such file or directory```

If You encounter an error like this, then just run the following commands
```bash
wget http://nz2.archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb
sudo dpkg -i libssl1.1_1.1.1f-1ubuntu2_amd64.deb
```
---

### 📦 Dependencies
```python-telegram```, ```python-dotenv```, ```os```, ```sys```, ```pickle```, ```shutil```, ```threading```, ```datetime```, ```subprocess```, ```time```

### 🤝 Contributions
Contributions, issues and feature requests are welcome!
Feel free to submit a PR or open an issue.

# Enjoy using TeleCopy! 🚀
