# JAPDP Deployment Guide — Demo Server (Windows VM + IIS)

This guide deploys JAPDP on a Windows VM for demonstration purposes. The result is a working instance of the platform accessible on the internal network.

Last updated: May 2026

---

## 1. What You Are Deploying

JAPDP has two parts:

- **Backend** — Python FastAPI server, runs on `127.0.0.1:8000`
- **Frontend** — Static React app, served by IIS

IIS does two things:
- Serves the built frontend files from `frontend-legacy/dist/`
- Forwards `/api/...` requests to the backend via reverse proxy

The `web.config` file in `frontend-legacy/public/` is automatically copied to `dist/` on every build. It contains the `API_Proxy` and `React_Fallback` rewrite rules — no manual rule setup in IIS is needed.

Users reach the app at `http://<vm-ip>/` or a hostname like `http://japdpvm/`.

---

## 2. Prerequisites

- A Windows VM (Windows Server 2019/2022 or Windows 10/11)
- Local administrator rights on the VM
- Access to the JAPDP Git repository
- A JAPBIMDB database (`.bak` backup file, or access to the live SQL Server instance)

### Database requirement

The platform reads structural element geometry from the existing `JAPBIMDB` SQL Server database (`dbo` schema, populated by Clarity). An empty SQL Server is not enough — you need a real database backup.

The backend connects via Windows Trusted Authentication:
```
mssql+pyodbc://{server}/JAPBIMDB?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes
```
The Windows account running the backend service must have read/write access to JAPBIMDB.

---

## 3. Software to Install

| Software | Purpose |
|---|---|
| Git | Clone the repo |
| Python 3.11+ | Run the backend |
| `uv` (Python package manager) | Install backend dependencies (`pip install uv`) |
| Node.js 22.x | Build the frontend |
| ODBC Driver 17 for SQL Server | Python → SQL Server connection |
| SQL Server Express or Developer | Host the database (skip if using an existing instance) |
| SQL Server Management Studio (SSMS) | Restore and manage the database |
| IIS | Serve the frontend |
| IIS URL Rewrite Module | Needed to process the `web.config` rewrite rules |
| Application Request Routing (ARR) | Needed for IIS to proxy `/api/...` to the backend |
| NSSM | Run the backend as a Windows service |

---

## 4. Enable IIS

Open Start → `Turn Windows features on or off`.

Under **Internet Information Services**, enable:
- Web Management Tools → IIS Management Console
- World Wide Web Services → Common HTTP Features → Static Content, Default Document, HTTP Errors
- World Wide Web Services → Security → Request Filtering

Click OK.

Then install **IIS URL Rewrite Module 2** and **Application Request Routing 3** (download from the IIS site or use Web Platform Installer). Close and reopen IIS Manager after installing.

---

## 5. Set Up the Database

### 5.1 Install SQL Server (skip if using an existing instance)

Install SQL Server Express or Developer. Note the instance name (e.g. `localhost\SQLEXPRESS`).

### 5.2 Restore JAPBIMDB

Open SSMS → right-click **Databases** → **Restore Database...** → choose the `.bak` file → restore as `JAPBIMDB`.

### 5.3 Run the platform schema script

In SSMS, open and run:
```
D:\JAP_DATA_PLATFORM\sql_migration_scripts\setup_db.sql
```

This creates the `management` and `design` schema tables. It checks for existing tables first — safe to run on any database that already has the `dbo` schema.

### 5.4 Verify

Confirm in SSMS that these exist:
- `dbo.Project`
- `management.project_meta`
- `design.load_tables`
- `design.rundown`

---

## 6. Clone the Repository

```powershell
cd D:\
git clone <REPO_URL> JAP_DATA_PLATFORM
```

---

## 7. Configure and Test the Backend

### 7.1 Create `.env`

```powershell
cd D:\JAP_DATA_PLATFORM\backend
copy .env.example .env
```

Edit `.env`:
```env
DB_SERVER=localhost\SQLEXPRESS
```

Use the actual SQL Server instance name on this VM.

### 7.2 Install dependencies

```powershell
uv sync
```

This creates `.venv` and installs all packages including `rundown_engine`.

### 7.3 Test the backend

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open in the VM browser: `http://127.0.0.1:8000/api/health`

Expected:
```json
{"status": "ok"}
```

Do not continue if this fails.

---

## 8. Build the Frontend

```powershell
cd D:\JAP_DATA_PLATFORM\frontend-legacy
npm ci
npm run build
```

Output goes to `D:\JAP_DATA_PLATFORM\frontend-legacy\dist\`.

The build automatically includes `web.config` (from `public/web.config`), which contains the `API_Proxy` and `React_Fallback` rewrite rules for IIS.

---

## 9. Enable ARR Proxy (server-level, one-time)

This is required for IIS to forward `/api/...` to the backend. Do this once per server.

In IIS Manager:
1. Click the **server node** (not the website) in the left panel
2. Double-click **Application Request Routing Cache**
3. Right panel → **Server Proxy Settings**
4. Check **Enable proxy** → click **Apply**

---

## 10. Create the IIS Website

In IIS Manager → left panel → right-click **Sites** → **Add Website...**

| Field | Value |
|---|---|
| Site name | `JAPDP` |
| Physical path | `D:\JAP_DATA_PLATFORM\frontend-legacy\dist` |
| Type | `http` |
| Port | `80` |
| Host name | *(leave blank, or enter the VM hostname)* |

Click OK. The `web.config` already in `dist/` handles all routing automatically.

---

## 11. Run the Backend as a Windows Service

Open an **elevated** PowerShell:

```powershell
nssm install JAPDP-Backend
```

In the NSSM GUI:
- **Application path:** `D:\JAP_DATA_PLATFORM\backend\.venv\Scripts\python.exe`
- **Startup directory:** `D:\JAP_DATA_PLATFORM\backend`
- **Arguments:** `-m uvicorn app.main:app --host 127.0.0.1 --port 8000`

Click **Install service**, then:

```powershell
nssm start JAPDP-Backend
sc query JAPDP-Backend
```

The backend now starts automatically on VM boot.

---

## 12. Open Firewall

```powershell
netsh advfirewall firewall add rule name="JAPDP HTTP" dir=in action=allow protocol=TCP localport=80
```

---

## 13. Access Control (optional)

By default the site is open to anyone who can reach port 80. This is fine for an internal demo.

To restrict to specific domain users:
1. IIS Manager → **JAPDP** site → **Authentication** → disable `Anonymous`, enable `Windows Authentication`
2. **Authorization Rules** → add an Allow Rule for e.g. `YOURDOMAIN\JAPDP_Users`

---

## 14. Final Verification

| Test | URL | Expected |
|---|---|---|
| Backend direct | `http://127.0.0.1:8000/api/health` | `{"status":"ok"}` |
| Backend via IIS | `http://localhost/api/health` | `{"status":"ok"}` |
| Frontend root | `http://localhost/` | App loads |
| React route refresh | `http://localhost/projects` → refresh | No 404 |
| Remote access | `http://<vm-ip>/` from another machine | App loads |

---

## 15. Updating the Demo Server

### Pull latest code
```powershell
cd D:\JAP_DATA_PLATFORM
git pull
```

### Restart backend after code changes
```powershell
nssm restart JAPDP-Backend
```

### Rebuild frontend after frontend changes
```powershell
cd D:\JAP_DATA_PLATFORM\frontend-legacy
npm ci
npm run build
```
No IIS restart needed — IIS reads from `dist/` directly.

### Apply new DB changes
Run any new SQL from `sql_migration_scripts/` in SSMS against JAPBIMDB.

---

## 16. Troubleshooting

**`URL Rewrite` not visible in IIS**
→ Install IIS URL Rewrite Module 2, then reopen IIS Manager.

**`/api/health` works on port 8000 but not via IIS (`http://localhost/api/health`)**
→ ARR proxy not enabled at the server level (Step 9). Check that `Enable proxy` is checked in Application Request Routing Cache → Server Proxy Settings.

**Frontend loads but deep routes give 404 on refresh**
→ `web.config` is missing from `dist/`. Run `npm run build` again — it copies `public/web.config` to `dist/`.

**Backend cannot connect to SQL Server**
→ Check `.env` `DB_SERVER` value. Test the connection in SSMS using the same Windows account the NSSM service runs as. Confirm `JAPBIMDB` exists and the account has `db_datareader` + `db_datawriter`.

**App loads but shows no projects**
→ `dbo.Project` is empty. The `dbo` schema requires Clarity data. Confirm with SSMS: `SELECT TOP 10 * FROM dbo.Project`.

**NSSM service fails to start**
→ Run `nssm edit JAPDP-Backend` → Logs tab to check the log path. Common causes: wrong Python path (check `.venv` exists), missing `.env`, SQL Server not running.
