# New Backend - Start Guide

## 🚀 Quick Start

### Using PowerShell (Recommended)
```powershell
cd d:\home_ss\new_backend
.\start.ps1
```

### Using Command Prompt
```cmd
cd d:\home_ss\new_backend
start.bat
```

---

## 📝 Manual Start (Step by Step)

### 1. Navigate to new_backend folder
```powershell
cd d:\home_ss\new_backend
```

### 2. Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

You should see `(venv)` at the start of your prompt:
```
(venv) PS D:\home_ss\new_backend>
```

### 3. Start the Backend Server
```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## ✅ Success Indicators

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [XXXXX] using WatchFiles
INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

---

## 🌐 Access the Backend

- **API Docs:** http://localhost:8000/docs
- **Alternative Docs:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health
- **WebSocket (Voice):** ws://localhost:8000/ws/voice

---

## 🔧 Troubleshooting

### Problem: "Execution of scripts is disabled"
**Solution:** Run this first:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Problem: "venv not found"
**Solution:** Set up virtual environment:
```powershell
.\setup_venv.ps1
```

### Problem: Port 8000 already in use
**Solution:** Find and kill the process:
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace XXXX with PID)
taskkill /PID XXXX /F
```

Or use a different port:
```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Problem: Missing dependencies
**Solution:** Install requirements:
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 🛑 Stop the Backend

Press `CTRL + C` in the terminal where it's running

---

## 📊 Check Backend Status

### From Browser
Visit: http://localhost:8000/health

### From PowerShell
```powershell
curl http://localhost:8000/health
```

### From Another Terminal
```powershell
Test-NetConnection -ComputerName localhost -Port 8000
```

---

## 🔄 Restart Backend

1. Stop with `CTRL + C`
2. Start again:
```powershell
.\start.ps1
```

---

## 📱 Connect ESP32

Once backend is running, update ESP32 code with your computer's IP:

### Find Your IP Address:
```powershell
ipconfig
```

Look for "IPv4 Address" under your active network adapter (usually starts with 192.168.x.x)

### Update ESP32 Code:
```cpp
const char* BACKEND_IP = "192.168.x.x";  // Your computer's IP
```

---

## 🐛 Debug Mode

### Enable Detailed Logging:
```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
```

### View All Endpoints:
Visit: http://localhost:8000/docs

---

## 📦 Environment Variables

Check `.env` file for configuration:
```
GEMINI_API_KEY=your_key_here
ENVIRONMENT=development
LOG_LEVEL=INFO
```

---

## ⚡ One-Line Commands

### Start Backend (PowerShell)
```powershell
cd d:\home_ss\new_backend ; .\start.ps1
```

### Start Backend (CMD)
```cmd
cd /d d:\home_ss\new_backend && start.bat
```

### Start with Custom Port
```powershell
cd d:\home_ss\new_backend ; .\venv\Scripts\Activate.ps1 ; python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

---

## 🎯 Testing the Backend

### Test Health Endpoint
```powershell
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"healthy","timestamp":"2024-..."}
```

### Test WebSocket Connection
Use the ESP32 Voice Assistant V3 code to connect!

---

## 💡 Pro Tips

1. **Keep terminal open** - Backend logs show all requests
2. **Use --reload flag** - Auto-restarts on code changes
3. **Check firewall** - Allow Python through Windows Firewall
4. **Use same WiFi** - ESP32 and computer must be on same network
5. **Note your IP** - It might change, especially on WiFi
