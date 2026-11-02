import streamlit as st
import pdfplumber
import pandas as pd
import gspread
import re
import json
import traceback
from calendar import monthrange
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
VALID_USERS = {
    "admin26": "@ellica987",
    "manager": "admin2026"
}
SECRET_ACCESS_CODE = "UKG2026"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1JP988S0UxEe6yLNwb5qxE2Pb47FgQCiCfbvIsW_qC7Q/edit?usp=sharing"

# ---------------------------------------------------------
# SESSION STATE MANAGEMENT
# ---------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "code_unlocked" not in st.session_state:
    st.session_state["code_unlocked"] = False

st.set_page_config(page_title="Team Schedule Portal", layout="centered")

# ---------------------------------------------------------
# STEP 1: LOGIN GATE
# ---------------------------------------------------------
if not st.session_state["authenticated"]:
    st.markdown("<h1 style='text-align: center;'>Team Schedule Portal</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Please Sign In</h3>", unsafe_allow_html=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns([6.8, 1])
    with col2:
        if st.button("Sign In"):
            if username in VALID_USERS and VALID_USERS[username] == password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Invalid Username or Password.")

# ---------------------------------------------------------
# STEP 2 & 3: ACCESS GATE & PDF UPLOADER
# ---------------------------------------------------------
else:
    st.markdown("<h1 style='text-align: center;'>Welcome to the Schedule Portal</h1>", unsafe_allow_html=True)

    col_out1, col_out2, col_out3 = st.columns([2.3, 1, 2.3])
    with col_out2:
        if st.button("Sign Out"):
            st.session_state["authenticated"] = False
            st.session_state["code_unlocked"] = False
            st.rerun()

    st.write("---")

    if not st.session_state["code_unlocked"]:
        st.markdown("<h3 style='text-align: center;'>Enter Access Code</h3>", unsafe_allow_html=True)
        entered_code = st.text_input("Enter security code:", type="password")
        
        col_btn1, col_btn2, col_btn3 = st.columns([2.3, 1, 2.3])
        with col_btn2:
            if st.button("Submit Code"):
                if entered_code == SECRET_ACCESS_CODE:
                    st.session_state["code_unlocked"] = True
                    st.rerun()
                else:
                    st.error("Incorrect Access Code.")
    else:
        st.success("Access Granted.")
        st.markdown(f"### [Click Here to Open Master Google Sheet]({GOOGLE_SHEET_URL})")
        st.write("---")

        # ---------------------------------------------------------
        # INDIVIDUAL UKG PDF UPLOADER & SPATIAL EXTRACTION
        # ---------------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>Upload Individual UKG Schedule PDF</h3>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose your individual schedule PDF:", type=["pdf"])

        if uploaded_file is not None:
            st.info("Reading PDF schedule layout and extracting shifts...")
            
            try:
                employee_name = None
                shift_records = []
                full_text = ""
                words_by_page = []

                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            full_text += extracted + "\n"
                        words_by_page.append(page.extract_words())

                # 1. UNIVERSAL DYNAMIC NAME EXTRACTION
                name_match = re.search(r'(?:JR|SJ|Employee|Name|Schedule for)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', full_text)
                if name_match:
                    extracted_candidate = name_match.group(1).strip()
                else:
                    lines = full_text.split('\n')
                    extracted_candidate = "Team Member"
                    for line in lines:
                        l_clean = line.strip()
                        if len(l_clean.split()) >= 2 and not any(m in l_clean for m in ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December", "schedule"]):
                            if any(initial in l_clean for initial in ["JR", "SJ", "AM", "MK", "JS", "DB"]):
                                extracted_candidate = re.sub(r'^(?:JR|SJ|AM|MK|JS|DB)\s*', '', l_clean).strip()
                                break
                
                employee_name = st.text_input("Confirm or edit detected employee full name:", value=extracted_candidate)

                # 2. MONTH & YEAR PARSER
                month_name = "November"
                year_str = "2026"
                
                date_range_match = re.search(r'(\d{4})-(\d{2})-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}', full_text)
                if date_range_match:
                    year_str = date_range_match.group(1)
                    month_num = int(date_range_match.group(2))
                    month_name = datetime(2026, month_num, 1).strftime('%B')

                month_short = month_name[:3]
                valid_shifts = {"EC", "ECG", "DCB1", "DCB2", "DHD", "DF", "N", "NC", "M1", "D1", "D2", "VP", "VAC"}

                # 3. SPATIAL & PROXIMITY EXTRACTION FOR MULTI-PAGE LAYOUTS
                seen_days = set()

                for page_words in words_by_page:
                    sorted_words = sorted(page_words, key=lambda w: (w['top'], w['x0']))
                    lines_grouped = []
                    current_line = []
                    last_top = None

                    for w in sorted_words:
                        if last_top is None or abs(w['top'] - last_top) < 12:
                            current_line.append(w)
                        else:
                            if current_line:
                                lines_grouped.append(current_line)
                            current_line = [w]
                        last_top = w['top']
                    if current_line:
                        lines_grouped.append(current_line)

                    for line in lines_grouped:
                        line_text_tokens = [w['text'].strip("[](),.") for w in line]
                        line_str = " ".join(line_text_tokens)
                        line_lower = line_str.lower()

                        if any(term in line_lower for term in ["remembrance", "holiday", "stat", "time-off", "approved", "opseu", "laboratory", "technologist", "0714"]):
                            continue

                        day_num_found = None
                        for token in line_text_tokens:
                            if token.isdigit() and 1 <= int(token) <= 31:
                                day_num_found = str(int(token))
                                break

                        shift_found = None
                        for token in line_text_tokens:
                            t_upper = token.upper()
                            if t_upper in valid_shifts:
                                shift_found = "VP" if t_upper in ["VAC", "VP"] else t_upper
                                break

                        if day_num_found and shift_found:
                            if day_num_found not in seen_days:
                                seen_days.add(day_num_found)
                                shift_records.append({
                                    "FullDate": f"{month_short} {day_num_found}, {year_str}",
                                    "DayNum": day_num_found,
                                    "Shift": shift_found
                                })

                flat_tokens = []
                for page_words in words_by_page:
                    sorted_w = sorted(page_words, key=lambda w: (w['top'], w['x0']))
                    for w in sorted_w:
                        flat_tokens.append(w['text'].strip("[](),."))

                for i, token in enumerate(flat_tokens):
                    if token.isdigit() and 1 <= int(token) <= 31:
                        d_num = str(int(token))
                        if d_num not in seen_days:
                            for offset in range(1, 6):
                                if i + offset < len(flat_tokens):
                                    candidate = flat_tokens[i + offset].upper()
                                    if candidate in valid_shifts:
                                        s_code = "VP" if candidate in ["VAC", "VP"] else candidate
                                        seen_days.add(d_num)
                                        shift_records.append({
                                            "FullDate": f"{month_short} {d_num}, {year_str}",
                                            "DayNum": d_num,
                                            "Shift": s_code
                                        })
                                        break

                # Sort chronologically by day number
                shift_records = sorted(shift_records, key=lambda x: int(x["DayNum"]))

                # 4. DISPLAY PREVIEW WITH MONTH & YEAR
                st.success(f"Detected Employee: **{employee_name}** | Schedule Period: **{month_name} {year_str}**")
                
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)[["FullDate", "Shift"]]
                    df_extracted.columns = ["Date", "Shift"]
                    st.write(f"Extracted Shifts Preview ({month_name} {year_str}):")
                    st.dataframe(df_extracted, hide_index=True)

                    if st.button("Sync to Google Sheet"):
                        try:
                            raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
                            if isinstance(raw_secret, str):
                                cred_dict = json.loads(raw_secret)
                            else:
                                cred_dict = dict(raw_secret)
                            
                            if "private_key" in cred_dict:
                                pk = cred_dict["private_key"]
                                pk = pk.replace("\\\\n", "\n").replace("\\n", "\n")
                                cred_dict["private_key"] = pk

                            gc = gspread.service_account_from_dict(cred_dict)
                            sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                            
                            data = sheet.get_all_values()
                            target_month_header = f"{month_name} {year_str}"
                            month_int = datetime.strptime(month_name, '%B').month
                            num_days = monthrange(int(year_str), month_int)[1]
                            
                            if len(data) < 2 or not data[0] or data[0][0] == "":
                                row1 = ["", target_month_header] + [""] * (num_days - 1)
                                row2 = ["Employee Name"] + [str(d) for d in range(1, num_days + 1)]
                                
                                sheet.update("A1", [row1, row2])
                                
                                requests_list = [
                                    {
                                        "updateDimensionProperties": {
                                            "range": {
                                                "sheetId": sheet.id,
                                                "dimension": "COLUMNS",
                                                "startIndex": 1,
                                                "endIndex": 2 + num_days
                                            },
                                            "properties": {"pixelSize": 35},
                                            "fields": "pixelSize"
                                        }
                                    }
                                ]
                                
                                for i in range(num_days):
                                    d = i + 1
                                    col_idx = 1 + i
                                    dt_obj = datetime(int(year_str), month_int, d)
                                    is_weekend = dt_obj.weekday() >= 5
                                    
                                    cell_format = {
                                        "borders": {
                                            "top": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}},
                                            "bottom": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}},
                                            "left": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}},
                                            "right": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}}
                                        }
                                    }
                                    fields_str = "userEnteredFormat.borders"
                                    
                                    if is_weekend:
                                        cell_format["backgroundColor"] = {"red": 0.85, "green": 0.85, "blue": 0.85}
                                        fields_str += ",userEnteredFormat.backgroundColor"
                                        
                                    requests_list.append({
                                        "repeatCell": {
                                            "range": {
                                                "sheetId": sheet.id,
                                                "startRowIndex": 0,
                                                "endRowIndex": 100,
                                                "startColumnIndex": col_idx,
                                                "endColumnIndex": col_idx + 1
                                            },
                                            "cell": {"userEnteredFormat": cell_format},
                                            "fields": fields_str
                                        }
                                    })
                                    
                                sheet.spreadsheet.batch_update({"requests": requests_list})
                                data = sheet.get_all_values()
                            else:
                                month_row = data[0]
                                month_exists = any(target_month_header.lower() in cell.lower() for cell in month_row)
                                
                                if not month_exists:
                                    current_max_col = max(len(row) for row in data)
                                    start_col_idx = current_max_col + 1
                                    
                                    for row in data:
                                        while len(row) < current_max_col + 1 + num_days:
                                            row.append("")
                                    
                                    start_col_letter = gspread.utils.rowcol_to_a1(1, start_col_idx)[0]
                                    end_col_idx = start_col_idx + num_days - 1
                                    
                                    sheet.update(f"{start_col_letter}1", [[target_month_header] + [""] * (num_days - 1)])
                                    sheet.update(f"{start_col_letter}2", [[str(d) for d in range(1, num_days + 1)]])
                                    
                                    requests_list = [
                                        {
                                            "updateDimensionProperties": {
                                                "range": {
                                                    "sheetId": sheet.id,
                                                    "dimension": "COLUMNS",
                                                    "startIndex": start_col_idx - 1,
                                                    "endIndex": end_col_idx
                                                },
                                                "properties": {"pixelSize": 35},
                                                "fields": "pixelSize"
                                            }
                                        }
                                    ]
                                    
                                    for i in range(num_days):
                                        d = i + 1
                                        col_idx = (start_col_idx - 1) + i
                                        dt_obj = datetime(int(year_str), month_int, d)
                                        is_weekend = dt_obj.weekday() >= 5
                                        
                                        cell_format = {
                                            "borders": {
                                                "top": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}},
                                                "bottom": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}},
                                                "left": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}},
                                                "right": {"style": "SOLID", "color": {"red": 0, "green": 0, "blue": 0}}
                                            }
                                        }
                                        fields_str = "userEnteredFormat.borders"
                                        
                                        if is_weekend:
                                            cell_format["backgroundColor"] = {"red": 0.85, "green": 0.85, "blue": 0.85}
                                            fields_str += ",userEnteredFormat.backgroundColor"
                                            
                                        requests_list.append({
                                            "repeatCell": {
                                                "range": {
                                                    "sheetId": sheet.id,
                                                    "startRowIndex": 0,
                                                    "endRowIndex": 100,
                                                    "startColumnIndex": col_idx,
                                                    "endColumnIndex": col_idx + 1
                                                },
                                                "cell": {"userEnteredFormat": cell_format},
                                                "fields": fields_str
                                            }
                                        })
                                        
                                    sheet.spreadsheet.batch_update({"requests": requests_list})
                                    data = sheet.get_all_values()

                            month_row = data[0] if len(data) > 0 else []
                            day_num_row = data[1] if len(data) > 1 else []
                            max_cols = max(len(month_row), len(day_num_row))
                            
                            emp_row_idx = None
                            target_row_data = None
                            for idx, row in enumerate(data):
                                if idx >= 2 and row and employee_name.lower() in row[0].lower():
                                    emp_row_idx = idx + 1
                                    target_row_data = list(row)
                                    break
                            
                            if not emp_row_idx:
                                target_row_data = [employee_name] + [""] * (max_cols - 1)
                                sheet.append_row(target_row_data)
                                data = sheet.get_all_values()
                                emp_row_idx = len(data)
                                target_row_data = list(data[emp_row_idx - 1])

                            while len(target_row_data) < max_cols:
                                target_row_data.append("")

                            updates_count = 0
                            current_active_month = month_name
                            
                            for record in shift_records:
                                target_day = record["DayNum"]
                                record_month_short = record["FullDate"].split()[0]
                                record_month_full = datetime.strptime(record_month_short, '%b').strftime('%B')
                                
                                matched_col_idx = None
                                active_month_tracker = current_active_month
                                
                                for col_idx in range(1, max_cols):
                                    if col_idx < len(month_row) and month_row[col_idx].strip():
                                        cell_val = month_row[col_idx].strip()
                                        if any(m in cell_val for m in ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]):
                                            active_month_tracker = cell_val
                                    
                                    if col_idx < len(day_num_row) and day_num_row[col_idx].strip() == target_day:
                                        if record_month_full.lower() in active_month_tracker.lower():
                                            matched_col_idx = col_idx
                                            break
                                
                                if matched_col_idx is None:
                                    for col_idx in range(1, max_cols):
                                        if col_idx < len(day_num_row) and day_num_row[col_idx].strip() == target_day:
                                            matched_col_idx = col_idx
                                            break

                                if matched_col_idx is not None:
                                    target_row_data[matched_col_idx] = record["Shift"]
                                    updates_count += 1

                            cell_range = f"A{emp_row_idx}:{gspread.utils.rowcol_to_a1(emp_row_idx, len(target_row_data))}"
                            sheet.update(cell_range, [target_row_data])
                            
                            st.success(f"Successfully updated {updates_count} shifts for {employee_name} in Master Sheet!")
                        except Exception as sheet_err:
                            err_details = traceback.format_exc()
                            st.error(f"Google Sheets sync error:\n{err_details}")
                else:
                    st.warning("No shift entries detected in this PDF schedule.")
                    
            except Exception as ex:
                st.error(f"Error processing spatial PDF: {ex}")
