import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from core import CFG, templates, BASE_DIR

app = FastAPI(title="Autopark Standalone")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Mock data for premium experience
veicoli = [
    {
        "id": 1,
        "modello": "Tesla Model 3",
        "targa": "GF345KK",
        "tipo": "Elettrica",
        "alimentazione_icon": "bi-lightning-charge-fill",
        "autonomia": "450 km (92%)",
        "posti": 5,
        "stato": "Disponibile",
        "stato_classe": "success",
        "colore": "#198754",
        "immagine": "https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=400&auto=format&fit=crop&q=60"
    },
    {
        "id": 2,
        "modello": "Audi A4 Avant",
        "targa": "FN123XX",
        "tipo": "Diesel (Mild Hybrid)",
        "alimentazione_icon": "bi-fuel-pump-fill",
        "autonomia": "850 km (75%)",
        "posti": 5,
        "stato": "In Uso",
        "stato_classe": "warning",
        "colore": "#fd7e14",
        "assegnato_a": "Mario Rossi",
        "rientro_previsto": "Oggi, ore 18:30",
        "immagine": "https://images.unsplash.com/photo-1606896328318-ee0877a94f6f?w=400&auto=format&fit=crop&q=60"
    },
    {
        "id": 3,
        "modello": "Fiat 500 Hybrid",
        "targa": "GE987YY",
        "tipo": "Ibrida",
        "alimentazione_icon": "bi-fuel-pump-fill",
        "autonomia": "320 km (45%)",
        "posti": 4,
        "stato": "Disponibile",
        "stato_classe": "success",
        "colore": "#198754",
        "immagine": "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?w=400&auto=format&fit=crop&q=60"
    },
    {
        "id": 4,
        "modello": "Jeep Compass 4xe",
        "targa": "GJ567ZZ",
        "tipo": "Plug-in Hybrid",
        "alimentazione_icon": "bi-lightning-charge-fill",
        "autonomia": "45 km (elettrico) / 500 km",
        "posti": 5,
        "stato": "In Manutenzione",
        "stato_classe": "danger",
        "colore": "#dc3545",
        "immagine": "https://images.unsplash.com/photo-1579250280907-73d810842cae?w=400&auto=format&fit=crop&q=60"
    }
]

prenotazioni_attive = [
    {
        "veicolo": "Audi A4 Avant (FN123XX)",
        "operatore": "Mario Rossi",
        "inizio": "Oggi, ore 08:30",
        "fine": "Oggi, ore 18:30",
        "destinazione": "Sede Cliente Milano"
    },
    {
        "veicolo": "Fiat 500 Hybrid (GE987YY)",
        "operatore": "Luigi Bianchi",
        "inizio": "Domani, ore 09:00",
        "fine": "Domani, ore 13:00",
        "destinazione": "Ufficio Postale centrale"
    }
]

@app.get("/appautopark", response_class=HTMLResponse)
def get_appautopark(r: Request):
    if "user" not in r.session: 
        return RedirectResponse(url="http://localhost:5001/login")
    user = r.session.get("user")
    
    return templates.TemplateResponse(r, "appautopark.html", {
        "request": r,
        "cfg": CFG,
        "user": user,
        "veicoli": veicoli,
        "prenotazioni": prenotazioni_attive
    })

@app.get("/")
def home_redirect():
    return RedirectResponse(url="/appautopark")
