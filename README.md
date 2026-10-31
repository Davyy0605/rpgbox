# RPGBox

Site Django, com foco no celular, para mestres de RPG.

## Desenvolvimento

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/playwright install chromium
.venv/Scripts/pytest
```

## JavaScript

`static/js/app.js` é gerado a partir de `frontend/` e fica versionado, então rodar o site não exige Node.
Só quem mexe em `frontend/` precisa de Node:

```
cd frontend
npm install
npm run build
```

Depois do build, faça o commit de `static/js/app.js` junto com o código.
