import sys
import os
import uvicorn

# Imposta il percorso del modulo per il backend Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("[*] Avvio Server API Python FastAPI per Troubletick PWA Ionic SPA...")
    print("[*] Endpoint API: http://localhost:8000/api")
    print("[*] Documentazione Swagger UI: http://localhost:8000/docs")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
