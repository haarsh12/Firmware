$ErrorActionPreference = "Stop"
$python = "C:\Users\LOQ\AppData\Local\Programs\Python\Python311\python.exe"

& $python -c "import httpx, json; health=httpx.get('http://127.0.0.1:8000/health', timeout=10).json(); print(json.dumps(health['xiaozhi_outbound_bridge'], indent=2)); print('relay_board_connections =', health['relay_board_connections'])"
