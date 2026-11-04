import os
import urllib.parse
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import CFG, templates
from utils import current_user

router = APIRouter()

@router.get("/formazione", response_class=HTMLResponse)
def get_formazione_page(r: Request):
    user = current_user(r)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Se il modulo è disabilitato da admin, reindirizza alla home con messaggio
    if not CFG.get("modulo_formazione", False):
        msg = urllib.parse.quote("Il modulo Formazione non è attualmente abilitato.")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)
    
    return templates.TemplateResponse(r, "formazione_under_construction.html", {
        "request": r,
        "user": user,
        "cfg": CFG
    })

