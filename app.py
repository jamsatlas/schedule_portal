import streamlit as st
import pandas as pd
import json
import ast
import re
from datetime import datetime, time, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import schedule_parser

# --- PAGE CONFIG ---
st.set_page_config(page_title="UKG Schedule Portal", layout="centered")

# --- CREDENTIALS & CALENDAR CONFIG ---
try:
    USERS = {
        "admin26": st.secrets["credentials"]["COWORKER_PASSWORD"],
        "james1209": st.secrets["credentials"]["PERSONAL_PASSWORD"]
    }
    CALENDAR_ID_1 = st.secrets["calendars"]["calendar_id_1"]
    CALENDAR_ID_2 = st.secrets["calendars"]["calendar_id_2"]
except KeyError:
    st.error("Missing credentials or calendar IDs in Streamlit secrets.")
    st.stop()

SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- SESSION STATE INITIALIZATION ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None

def parse_shift_times(time_str):
    """Parses shift time ranges into datetime.time objects."""
    if not time_str or not isinstance(time_str, str) or "-" not in time_str:
        return time(9, 0), time(17, 0)
    
    parts = time_str.split("-")
    start_raw, end_raw = parts[0].strip(), parts[1].strip()
    
    def parse_single_time(t_str):
        t_str = t_str.lower().replace(" ", "")
        for fmt in ("%H:%M", "%I:%M%p", "%I%p", "%I:%M"):
            try:
                return datetime.strptime(t_str, fmt).time()
            except ValueError:
                pass
        return time(9, 0)
        
    return parse_single_time(start_raw), parse_single_time(end_raw)

def get_calendar_service():
    """Builds the Google Calendar API service with bulletproof private key cleaning."""
    raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
    
    if isinstance(raw_secret, dict):
        cred_dict = raw_secret
    else:
        try:
            cred_dict = json.loads(raw_secret)
        except Exception:
            try:
                cred_dict = ast.literal_eval(raw_secret)
            except Exception:
                cleaned_secret = raw_secret.replace('\n', '\\n').replace('\r', '')
                cred_dict = json.loads(cleaned_secret)
            
    if "private_key" in cred_dict:
        pk = str(cred_dict["private_key"])
        
        # Convert literal escaped newlines to real ones
        pk = pk.replace("\\n", "\n").replace(r"\n", "\n").replace("\\r", "")
        
        # Extract base64 content between headers if present
        match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
        key_content = match.group(1) if match else pk
        
        # Filter out all invalid symbols, keeping only valid base64 characters
        clean_chars = [char for char in key_content if char.isalnum() or char in "+/= \n\t"]
        base64_cleaned = "".join(clean_chars)
        base64_only = "".join(base64_cleaned.split())
        
        # Rebuild standard 64-character PEM format with real newlines
        chunks = [base64_only[i:i+64] for i in range(0, len(base64_only), 64)]
        cred_dict["private_key"] = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(chunks) + "\n-----END PRIVATE KEY-----\n"
        
    creds = Credentials.from_service_account_info(cred_dict, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def add_shifts_to_google_calendars(shift_records, target_calendar_ids):
    """Pushes parsed shifts directly into configured Google Calendars, 
    clearing out old shift events in that date range first to prevent duplicates."""
    service = get_calendar_service()
    
    if not shift_records:
        return 0

    valid_dates = []
    for rec in shift_records:
        date_val = rec.get("Date")
        if not date_val or isinstance(date_val, float):
            continue
        date_str = str(date_val).strip()
        if not date_str or date_str.lower() == 'nan':
            continue

        shift_code = str(rec.get("Shift Code", "")).strip()
        if shift_code and shift_code.upper() not in ["OFF", "VAC", "UNAVAIL"]:
            try:
                dt = datetime.strptime(date_str, "%b %d, %Y").date()
                valid_dates.append(dt)
            except ValueError:
                pass
                
    if not valid_dates:
        return 0
        
    min_date = min(valid_dates)
    max_date = max(valid_dates)
    
    time_min = datetime.combine(min_date, time.min).isoformat() + 'Z'
    time_max = datetime.combine(max_date + timedelta(days=1), time.max).isoformat() + 'Z'

    success_count = 0
    
    for cal_id in target_calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            existing_events = events_result.get('items', [])
            for event in existing_events:
                summary = event.get('summary', '')
                if summary.startswith("Work Shift:"):
                    service.events().delete(calendarId=cal_id, eventId=event['id']).execute()
        except Exception as cleanup_err:
            print(f"Warning during cleanup of old events: {cleanup_err}")

        for rec in shift_records:
            date_val = rec.get("Date")
            if not date_val or isinstance(date_val, float):
                continue
            date_str = str(date_val).strip()
            if not date_str or date_str.lower() == 'nan':
                continue

            shift_code = str(rec.get("Shift Code", "")).strip()
            if not shift_code or shift_code.upper() not in ["OFF", "VAC", "UNAVAIL"]:
                continue
                
            try:
                date_obj = datetime.strptime(date_str, "%b %d, %Y").date()
            except ValueError:
                continue

            time_range_val = rec.get("Time Range", "")
            time_range_str = str(time_range_val) if time_range_val is not None else ""
            start_t, end_t = parse_shift_times(time_range_str)
            
            start_datetime = datetime.combine(date_obj, start_t)
            end_datetime = datetime.combine(date_obj, end_t)
            
            if end_datetime <= start_datetime:
                end_datetime += timedelta(days=1)
                
            event_body = {
                'summary': f"Work Shift: {shift_code}",
                'description': f"UKG Shift Code: {shift_code}",
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'America/Toronto',
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'America/Toronto',
                },
            }

            service.events().insert(calendarId=cal_id, body=event_body).execute()
            success_count += 1

    return len(valid_dates)


# ==========================================
# 1. LOGIN SCREEN
# ==========================================
if not st.session_state["authenticated"]:
    st.markdown("<h1 style='text-align: center;'>Team Schedule Portal</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Please Sign In</h3>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username").strip()
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Sign In")
        
        if submit_button:
            if username in USERS and USERS[username] == password:
                st.session_state["authenticated"] = True
                st.session_state["current_user"] = username
                st.rerun()
            else:
                st.error("Invalid Username or Password.")

# ==========================================
# 2. MAIN APPLICATION (AUTHENTICATED)
# ==========================================
else:
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.markdown(f"### Signed in as: **`{st.session_state['current_user']}`**")
    with col_h2:
        if st.button("Sign Out"):
            st.session_state["authenticated"] = False
            st.session_state["current_user"] = None
            st.rerun()

    st.write("---")
    st.markdown("<h2 style='text-align: center;'>Upload UKG Schedule PDFs</h2>", unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader("Choose schedule PDF(s):", type=["pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        parsed_records = []
        
        for file in uploaded_files:
            try:
                pdf_bytes = file.getvalue()
                parsed = schedule_parser.parse_schedule(pdf_bytes)
                
                for s in parsed.get("shifts", []):
                    parsed_records.append({
                        "Date": s["date"].strftime("%b %d, %Y"),
                        "Day": str(s["date"].day),
                        "Shift Code": s["code"],
                        "Time Range": s.get("time", "")
                    })
            except Exception as e:
                st.error(f"Error parsing {file.name}: {e}")

        if parsed_records:
            st.success("Extracted shift breakdown below:")
            
            df_shifts = pd.DataFrame(parsed_records)
            edited_df = st.data_editor(
                df_shifts,
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic"
            )
            
            reconstructed_records = edited_df.to_dict(orient="records")
            st.write("---")

            # ==========================================
            # 3. EXPORT CONTROLS (ROLE-BASED)
            # ==========================================
            if st.session_state["current_user"] == "james1209":
                st.markdown("### 📅 Google Calendar Export")
                
                if st.button("🚀 Push Shifts directly to My 2 Google Calendars", type="primary", use_container_width=True):
                    with st.spinner("Syncing events to your configured Google Calendars..."):
                        try:
                            count = add_shifts_to_google_calendars(
                                reconstructed_records, 
                                [CALENDAR_ID_1, CALENDAR_ID_2]
                            )
                            st.success(f"Successfully exported shifts! (Replaced old shifts in date range to prevent duplicates).")
                        except Exception as sync_err:
                            st.error(f"Google Calendar Sync Error: {sync_err}")
            
            elif st.session_state["current_user"] == "admin26":
                st.info("ℹ️ Schedule preview loaded. External calendar export is restricted.")
