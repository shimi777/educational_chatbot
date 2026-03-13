# Setup Guide: Streamlit Cloud + Google Drive/Sheets

## Overview
Your app needs 3 things configured in Google Cloud:
1. **Service Account** — lets the app authenticate with Google
2. **Google Sheet** — stores sessions + evaluation scores
3. **Google Drive folder** — stores transcript `.txt` files

---

## PART 1 — Google Cloud Setup

### Step 1: Create a Google Cloud Project
1. Go to https://console.cloud.google.com
2. Click the project dropdown (top-left) → **New Project**
3. Name it (e.g. `educational-chatbot`) → **Create**

### Step 2: Enable the Required APIs
In your project, go to **APIs & Services → Library** and enable:
- **Google Sheets API**
- **Google Drive API**

### Step 3: Create a Service Account
1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → Service Account**
3. Name it (e.g. `chatbot-service`) → **Create and Continue** → **Done**
4. Click on the service account you just created
5. Go to the **Keys** tab → **Add Key → Create new key → JSON**
6. A `.json` file will download — **keep this safe, it's your credential file**

The file looks like:
```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
  "client_email": "chatbot-service@your-project.iam.gserviceaccount.com",
  ...
}
```
Copy the `client_email` value — you'll need it to share your Sheet/Drive folder.

---

## PART 2 — Google Sheets Setup

### Step 4: Create the Google Sheet
1. Go to https://sheets.google.com → **Blank spreadsheet**
2. Rename it (e.g. `Chatbot Data`)
3. You need **exactly 2 tabs** with these names:
   - Rename `Sheet1` to: **`Sessions`**
   - Add a second tab named: **`Evaluations`**

### Step 5: Add Column Headers

In the **Sessions** tab, add these headers in row 1:
| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| session_id | created_at | topic_name | settings_json | topic_config_json | lang | status |

In the **Evaluations** tab, add these headers in row 1:
| A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| session_id | student_name | timestamp | total_score | max_score | performance_level | core_statement | formal_form | conditions | mechanism | distinctions | example | misconceptions | misconceptions_count | notes | turns | mentor_consultations | lang |

### Step 6: Share the Sheet with the Service Account
1. Click the **Share** button (top-right)
2. Paste the service account's `client_email`
3. Set role to **Editor**
4. Uncheck "Notify people" → **Share**

### Step 7: Get the Spreadsheet ID
From the Sheet URL:
```
https://docs.google.com/spreadsheets/d/  <<THIS_IS_THE_ID>>  /edit
```
Copy and save it.

---

## PART 3 — Google Drive Setup

### Step 8: Create a Drive Folder
1. Go to https://drive.google.com
2. **+ New → New Folder**, name it (e.g. `Chatbot Transcripts`)

### Step 9: Share the Folder with the Service Account
1. Right-click the folder → **Share**
2. Paste the service account `client_email`
3. Role: **Editor** → **Share**

### Step 10: Get the Folder ID
From the folder URL:
```
https://drive.google.com/drive/folders/  <<THIS_IS_THE_FOLDER_ID>>
```
Copy and save it.

---

## PART 4 — Streamlit Cloud Deployment

### Step 11: Push Code to GitHub
Make sure your repo is on GitHub (branch `connection_to_cloud`). The `.env` file must **not** be committed (it's gitignored).

### Step 12: Deploy on Streamlit Cloud
1. Go to https://share.streamlit.io
2. Sign in with GitHub → **New app**
3. Select your repo + branch (`connection_to_cloud`)
4. Set **Main file path** to: `teacher_app.py` (for teacher) or `student_app.py` (for student)
5. Click **Advanced settings** before deploying

### Step 13: Add Secrets in Streamlit Cloud
In **Advanced settings → Secrets**, paste this (fill in your values):

```toml
OPENAI_API_KEY = "sk-your-key-here"
TEACHER_PASSWORD = "your-password"
STUDENT_APP_URL = "https://your-student-app.streamlit.app"
GOOGLE_SPREADSHEET_ID = "your-spreadsheet-id"
GOOGLE_DRIVE_FOLDER_ID = "your-drive-folder-id"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "chatbot-service@your-project.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

> The `[gcp_service_account]` block is the **entire contents** of the downloaded JSON file, converted to TOML format.

6. Click **Deploy**

---

## PART 5 — Local Development

### Step 14: Configure Local `.env`
Edit your `.env` file (already exists in project root):

```env
OPENAI_API_KEY=sk-your-key-here
GOOGLE_SPREADSHEET_ID=your-spreadsheet-id
GOOGLE_DRIVE_FOLDER_ID=your-drive-folder-id
GOOGLE_CREDENTIALS_FILE=path/to/your-service-account.json
TEACHER_PASSWORD=your-password
STUDENT_APP_URL=http://localhost:8502
```

---

## Summary — What Each Value Is

| Variable | Where to find it |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `GOOGLE_SPREADSHEET_ID` | Sheet URL between `/d/` and `/edit` |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive folder URL after `/folders/` |
| `GOOGLE_CREDENTIALS_FILE` | Path to downloaded `.json` file (local only) |
| `[gcp_service_account]` | Contents of the `.json` file (Streamlit Cloud only) |
| `TEACHER_PASSWORD` | Any password you choose |
| `STUDENT_APP_URL` | The deployed student app URL on Streamlit Cloud |
