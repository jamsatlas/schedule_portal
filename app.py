import streamlit as st
import pandas as pd
import gspread
import json
import ast
import re
import traceback
from calendar import monthrange
from datetime import datetime, date, time, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import schedule_parser

# --- PAGE CONFIG ---
st.set_page_config(page_title="Team Schedule Portal", layout="centered")

# --- CREDENTIALS & CONFIG ---
try:
    USERS = {
        "admin26": st.secrets["credentials"]["COWORKER_PASSWORD"],
        "james1209": st.secrets["credentials"]["PERSONAL_PASSWORD"]
    }
    CALENDAR_ID_1 = st.secrets["calendars"]["calendar_id_1"]
    CALENDAR_ID_2 = st.secrets["calendars"]["calendar_id_2"]
    
    GOOGLE_SHEET_URL = ""
    if "google_sheets" in st.secrets and "sheet_url" in st.secrets["google_sheets"]:
        GOOGLE_SHEET_URL = st.secrets["google_sheets"]["sheet_url"]
    else:
        GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1JP988S0UxEe6yLNwb5qxE2Pb47FgQCiCfbvIsW_qC7Q/edit?usp=sharing"
        
except KeyError:
    st.error("Missing credentials or IDs in Streamlit secrets.")
    st.stop()

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# --- SESSION STATE INITIALIZATION ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None


# ==========================================
# SANITIZED AUTHENTICATION & SERVICES
# ==========================================
def get_google_credentials():
    """Builds Google credentials with bulletproof private key cleaning."""
    raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
    if isinstance(raw_secret, dict):
        cred_dict = dict(raw_secret)
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
        pk = pk.replace("\\n", "\n").replace(r"\n", "\n").replace("\\r", "")
        match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
        key_content = match.group(1) if match else pk
        
        clean_chars = [char for char in key_content if char.isalnum() or char in "+/= \n\t"]
        base64_cleaned = "".join(clean_chars)
        base64_only = "".join(base64_cleaned.split())
        
        chunks = [base64_only[i:i+64] for i in range(0, len(base64_only), 64)]
        cred_dict["private_key"] = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(chunks) + "\n-----END PRIVATE KEY-----\n"
        
    return Credentials.from_service_account_info(cred_dict, scopes=SCOPES)

def get_calendar_service():
    creds = get_google_credentials()
    return build('calendar', 'v3', credentials=creds)

def get_sheets_client():
    creds = get_google_credentials()
    return gspread.authorize(creds)


# ==========================================
# ORIGINAL GOOGLE SHEETS GRID ENGINE
# ==========================================
def parse_existing_sheet(data):
    if len(data) < 2:
        return [], {}
        
    row1 = data[0]
    row2 = data[1]
    
    employees = []
    for r in range(2, len(data)):
        if data[r] and data[r][0].strip():
            emp = data[r][0].strip()
            if emp not in employees:
                employees.append(emp)

    months = {}
    total_cols = len(row2)
    c = 1
    while c < total_cols:
        month_found = None
        for col_idx in range(c, total_cols):
            val = row1[col_idx].strip() if col_idx < len(row1) else ""
            if val:
                try:
                    parts = val.split()
                    if len(parts) >= 2:
                        m_str, y_str = parts[0], parts[1]
                        m_int = datetime.strptime(m_str, "%B").month
                        y_int = int(y_str)
                        month_found = (col_idx, val, y_int, m_int)
                        break
                except Exception:
                    pass
        if not month_found:
            break
            
        start_c, title, yr, mo = month_found
        n_days = monthrange(yr, mo)[1]
        
        emp_shifts = {}
        for emp in employees:
            emp_row = None
            for r in range(2, len(data)):
                if data[r] and data[r][0].strip().lower() == emp.lower():
                    emp_row = data[r]
                    break
            
            shifts_list = []
            for d in range(1, n_days + 1):
                col_i = start_c + (d - 1)
                val = ""
                if emp_row and col_i < len(emp_row):
                    val = emp_row[col_i].strip()
                shifts_list.append(val)
            emp_shifts[emp] = shifts_list
            
        months[(yr, mo)] = {
            'title': title,
            'num_days': n_days,
            'employee_shifts': emp_shifts
        }
        c = start_c + n_days
        
    return employees, months

def rebuild_sheet_grid(employees, months):
    sorted_month_keys = sorted(months.keys())
    
    row1 = [""]
    row2 = ["Employee Name"]
    
    for key in sorted_month_keys:
        m_info = months[key]
        n_days = m_info['num_days']
        row1.extend([m_info['title']] + [""] * (n_days - 1))
        row2.extend([str(d) for d in range(1, n_days + 1)])
        
    grid = [row1, row2]
    
    for emp in employees:
        emp_row = [emp]
        for key in sorted_month_keys:
            m_info = months[key]
            emp_shifts = m_info['employee_shifts'].get(emp, [""] * m_info['num_days'])
            emp_row.extend(emp_shifts)
        grid.append(emp_row)
        
    return grid

def apply_full_schedule_formatting(spreadsheet, sheet, data):
    if len(data) < 2:
        return
    
    row1 = data[0]
    row2 = data[1]
    total_cols = len(row2)
    max_rows = max(len(data) + 10, 30)
    
    requests = []

    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet.id,
                "gridProperties": {
                    "frozenRowCount": 2,
                    "frozenColumnCount": 1
                }
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
        }
    })

    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet.id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 1
            },
            "properties": {"pixelSize": 180},
            "fields": "pixelSize"
        }
    })
    
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet.id,
                "startRowIndex": 1,
                "endRowIndex": max_rows,
                "startColumnIndex": 0,
                "endColumnIndex": 1
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "LEFT",
                    "verticalAlignment": "MIDDLE",
                    "borders": {
                        "top": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                        "bottom": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                        "left": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                        "right": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}}
                    }
                }
            },
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,borders)"
        }
    })

    c = 1
    while c < total_cols:
        month_found = None
        for col_idx in range(c, total_cols):
            val = row1[col_idx].strip() if col_idx < len(row1) else ""
            if val:
                try:
                    parts = val.split()
                    if len(parts) >= 2:
                        m_str, y_str = parts[0], parts[1]
                        m_int = datetime.strptime(m_str, "%B").month
                        y_int = int(y_str)
                        month_found = (col_idx, val, y_int, m_int)
                        break
                except Exception:
                    pass

        if not month_found:
            break

        start_c, month_title, yr, mo = month_found
        n_days = monthrange(yr, mo)[1]
        end_c = min(start_c + n_days, total_cols)

        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet.id,
                    "dimension": "COLUMNS",
                    "startIndex": start_c,
                    "endIndex": end_c
                },
                "properties": {"pixelSize": 38},
                "fields": "pixelSize"
            }
        })

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": max_rows,
                    "startColumnIndex": start_c,
                    "endColumnIndex": end_c
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "borders": {
                            "top": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                            "bottom": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                            "left": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                            "right": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}}
                        }
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,borders)"
            }
        })

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": start_c,
                    "endColumnIndex": start_c + 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 11},
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": start_c,
                    "endColumnIndex": end_c
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        for d in range(1, n_days + 1):
            col_pos = start_c + (d - 1)
            if col_pos >= total_cols:
                break
            dt = date(yr, mo, d)
            if dt.weekday() in (5, 6):
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet.id,
                            "startRowIndex": 1,
                            "endRowIndex": max_rows,
                            "startColumnIndex": col_pos,
                            "endColumnIndex": col_pos + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor"
                    }
                })

        c = end_c

    if requests:
        spreadsheet.batch_update({"requests": requests})


# ==========================================
# GOOGLE CALENDAR SYNC ENGINE (FOR JAMES)
# ==========================================
def parse_shift_times(time_str):
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

def add_shifts_to_google_calendars(shift_records, target_calendar_ids):
    service = get_calendar_service()
    if not shift_records: return 0

    valid_dates = []
    for rec in shift_records:
        date_val = rec.get("Date") or rec.get("FullDate")
        if not date_val or isinstance(date_val, float): continue
        date_str = str(date_val).strip()
        if not date_str or date_str.lower() == 'nan': continue

        shift_code = str(rec.get("Shift Code") or rec.get("Shift", "")).strip()
        if shift_code and shift_code.upper() not in ["OFF", "VAC", "UNAVAIL"]:
            try:
                valid_dates.append(datetime.strptime(date_str, "%b %d, %Y").date())
            except ValueError:
                pass
                
    if not valid_dates: return 0
        
    min_date = min(valid_dates)
    max_date = max(valid_dates)
    time_min = datetime.combine(min_date, time.min).isoformat() + 'Z'
    time_max = datetime.combine(max_date + timedelta(days=1), time.max).isoformat() + 'Z'

    success_count = 0
    
    for cal_id in target_calendar_ids:
        try:
            events_result = service.events().list(calendarId=cal_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            for event in events_result.get('items', []):
                if event.get('summary', '').startswith("Work Shift:"):
                    service.events().delete(calendarId=cal_id, eventId=event['id']).execute()
        except Exception as cleanup_err:
            print(f"Warning during cleanup of old events: {cleanup_err}")

        for rec in shift_records:
            date_val = rec.get("Date") or rec.get("FullDate")
            shift_code = str(rec.get("Shift Code") or rec.get("Shift", "")).strip()
            
            if not date_val or isinstance(date_val, float) or not shift_code or shift_code.upper() in ["OFF", "VAC", "UNAVAIL"]:
                continue
                
            try:
                date_obj = datetime.strptime(str(date_val).strip(), "%b %d, %Y").date()
            except ValueError:
                continue

            time_range_str = str(rec.get("Time Range") or rec.get("Time", ""))
            start_t, end_t = parse_shift_times(time_range_str)
            start_datetime = datetime.combine(date_obj, start_t)
            end_datetime = datetime.combine(date_obj, end_t)
            
            if end_datetime <= start_datetime: end_datetime += timedelta(days=1)
                
            event_body = {
                'summary': f"Work Shift: {shift_code}",
                'description': f"UKG Shift Code: {shift_code}",
                'start': {'dateTime': start_datetime.isoformat(), 'timeZone': 'America/Toronto'},
                'end': {'dateTime': end_datetime.isoformat(), 'timeZone': 'America/Toronto'},
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
    st.markdown(f"### 🔗 [Click Here to Open Master Google Sheet]({GOOGLE_SHEET_URL})")
    st.write("---")
    st.markdown("<h2 style='text-align: center;'>Upload UKG Schedule PDFs</h2>", unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader("Choose one or multiple individual schedule PDFs:", type=["pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        st.info(f"Processing {len(uploaded_files)} PDF schedule(s)...")
        
        parsed_batch = []
        
        for idx, file in enumerate(uploaded_files):
            try:
                pdf_bytes = file.getvalue()
                parsed = schedule_parser.parse_schedule(pdf_bytes)
                emp_name = parsed.get("name", f"Employee {idx+1}")
                start_dt = parsed.get("start")
                
                if not start_dt:
                    st.warning(f"Could not find schedule date range in {file.name}. Skipping.")
                    continue
                    
                shift_recs = []
                for s in parsed.get("shifts", []):
                    shift_recs.append({
                        "FullDate": s["date"].strftime("%b %d, %Y"),
                        "DayNum": str(s["date"].day),
                        "Shift": s["code"],
                        "Time": s.get("time", "")
                    })
                    
                parsed_batch.append({
                    "file_id": f"file_{idx}",
                    "filename": file.name,
                    "employee_name": emp_name,
                    "start_date": start_dt,
                    "month_name": start_dt.strftime("%B"),
                    "year_str": str(start_dt.year),
                    "shift_records": shift_recs
                })
            except Exception as parse_err:
                st.error(f"Error parsing {file.name}: {parse_err}")

        if parsed_batch:
            st.success(f"Successfully extracted {len(parsed_batch)} schedule(s)! Review each schedule table below:")
            
            edited_batch = []
            
            for item in parsed_batch:
                exp_title = f"📋 {item['employee_name']} — {item['month_name']} {item['year_str']} ({item['filename']})"
                with st.expander(exp_title, expanded=True):
                    emp_name_edited = st.text_input(
                        f"Employee Name ({item['filename']}):",
                        value=item["employee_name"],
                        key=f"name_{item['file_id']}"
                    )
                    
                    df_shifts = pd.DataFrame(item["shift_records"])
                    df_shifts = df_shifts[["FullDate", "DayNum", "Shift", "Time"]]
                    df_shifts.columns = ["Date", "Day", "Shift Code", "Time Range"]
                    
                    st.markdown("**Shift Breakdown (Double-click any Shift Code cell to edit if needed):**")
                    edited_df = st.data_editor(
                        df_shifts,
                        key=f"editor_{item['file_id']}",
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    reconstructed_records = []
                    for _, row in edited_df.iterrows():
                        reconstructed_records.append({
                            "FullDate": row["Date"],
                            "DayNum": str(row["Day"]),
                            "Shift": str(row["Shift Code"]).strip(),
                            "Time": str(row["Time Range"]).strip()
                        })
                        
                    edited_batch.append({
                        "employee_name": emp_name_edited.strip(),
                        "start_date": item["start_date"],
                        "month_name": item["month_name"],
                        "year_str": item["year_str"],
                        "shift_records": reconstructed_records
                    })

            st.write("---")

            # ==========================================
            # 3. EXPORT CONTROLS (ROLE-BASED)
            # ==========================================
            
            # --- JAMES WORKFLOW (CALENDAR SYNC) ---
            if st.session_state["current_user"] == "james1209":
                st.markdown("### 📅 Google Calendar Export")
                
                if st.button("🚀 Push Shifts directly to My 2 Google Calendars", type="primary", use_container_width=True):
                    with st.spinner("Syncing events to your configured Google Calendars..."):
                        try:
                            all_shifts = []
                            for b in edited_batch:
                                all_shifts.extend(b["shift_records"])
                            count = add_shifts_to_google_calendars(all_shifts, [CALENDAR_ID_1, CALENDAR_ID_2])
                            st.success(f"Successfully exported shifts to both Google Calendars!")
                        except Exception as sync_err:
                            st.error(f"Google Calendar Sync Error: {sync_err}")
            
            # --- COWORKER WORKFLOW (GRID ENGINE GOOGLE SHEETS) ---
            elif st.session_state["current_user"] == "admin26":
                st.markdown("### 📊 Google Sheets Export")
                
                if st.button("Sync All Schedules to Master Google Sheet", type="primary", use_container_width=True):
                    with st.spinner("Syncing schedule data to the Master Google Sheet..."):
                        try:
                            gc = get_sheets_client()
                            spreadsheet = gc.open_by_url(GOOGLE_SHEET_URL)
                            
                            by_year = {}
                            for item in edited_batch:
                                yr = item["year_str"]
                                if yr not in by_year:
                                    by_year[yr] = []
                                by_year[yr].append(item)
                                
                            for year_tab_name, items in by_year.items():
                                try:
                                    sheet = spreadsheet.worksheet(year_tab_name)
                                except Exception:
                                    sheet = spreadsheet.add_worksheet(title=year_tab_name, rows=100, cols=400)
                                
                                raw_data = sheet.get_all_values()
                                employees, months_dict = parse_existing_sheet(raw_data)
                                
                                for item in items:
                                    emp_name = item["employee_name"]
                                    start_dt = item["start_date"]
                                    m_name = item["month_name"]
                                    y_str = item["year_str"]
                                    shift_recs = item["shift_records"]
                                    
                                    if emp_name not in employees:
                                        employees.append(emp_name)
                                        
                                    current_year = start_dt.year
                                    current_month = start_dt.month
                                    month_key = (current_year, current_month)
                                    target_month_title = f"{m_name} {y_str}"
                                    num_days = monthrange(current_year, current_month)[1]
                                    
                                    if month_key not in months_dict:
                                        months_dict[month_key] = {
                                            'title': target_month_title,
                                            'num_days': num_days,
                                            'employee_shifts': {}
                                        }
                                    
                                    shifts_array = months_dict[month_key]['employee_shifts'].get(emp_name, [""] * num_days)
                                    for rec in shift_recs:
                                        try:
                                            d_idx = int(rec["DayNum"]) - 1
                                            if 0 <= d_idx < num_days:
                                                shifts_array[d_idx] = rec["Shift"]
                                        except ValueError:
                                            continue
                                            
                                    months_dict[month_key]['employee_shifts'][emp_name] = shifts_array
                                
                                for emp in employees:
                                    for mk in months_dict:
                                        if emp not in months_dict[mk]['employee_shifts']:
                                            months_dict[mk]['employee_shifts'][emp] = [""] * months_dict[mk]['num_days']
                                            
                                new_grid = rebuild_sheet_grid(employees, months_dict)
                                
                                required_cols = len(new_grid[0])
                                if sheet.col_count < required_cols:
                                    sheet.add_cols(required_cols - sheet.col_count)
                                
                                sheet.clear()
                                sheet.update("A1", new_grid)
                                apply_full_schedule_formatting(spreadsheet, sheet, new_grid)

                            st.success(f"Successfully synced all {len(edited_batch)} schedule(s) to Master Sheet!")
                        except Exception as sheet_err:
                            st.error(f"Google Sheets sync error:\n{traceback.format_exc()}")
