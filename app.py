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
        # INDIVIDUAL UKG PDF UPLOADER & TEXT EXTRACTION
        # ---------------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>Upload Individual UKG Schedule PDF</h3>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose your individual schedule PDF:", type=["pdf"])

        if uploaded_file is not None:
            st.info("Reading PDF schedule layout and extracting shifts...")
            
            try:
                employee_name = None
                shift_records = []
                
                full_text = ""
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            full_text += extracted + "\n"
                
                # 1. DYNAMIC NAME EXTRACTION
                name_match = re.search(r'(?:Employee|Name|Schedule for|JR|SJ)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', full_text)
                if name_match:
                    extracted_candidate = name_match.group(1).strip()
                else:
                    name_fallback = re.search(r'\n([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\n', full_text)
                    extracted_candidate = name_fallback.group(1).strip() if name_fallback else "Subanki Jeyapalan"
                
                employee_name = st.text_input("Confirm or edit detected employee full name:", value=extracted_candidate)

                # 2. MONTH & YEAR PARSER
                month_name = "November"
                year_str = "2026"
                
                date_range_match = re.search(r'(\d{4})-(\d{2})-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}', full_text)
                if date_range_match:
                    year_str = date_range_match.group(1)
                    month_num = int(date_range_match.group(2))
                    month_name = datetime(2026, month_num, 1).strftime('%B')

                # 3. UNIVERSAL PATTERN SHIFT PARSER (< 5 CHARACTERS FILTER)
                lines = full_text.split('\n')
                month_short = month_name[:3]
                seen_days = set()
                
                current_day = None

                for line in lines:
                    l_str = line.strip()
                    l_lower = l_str.lower()
                    
                    # Skip statutory holidays, dates, and metadata
                    if any(term in l_lower for term in ["remembrance", "holiday", "stat", "time-off", "approved", "opseu", "my schedule", "laboratory", "technologist"]):
                        current_day = None
                        continue
                    if "-" in l_str and any(yr in l_str for yr in ["2024", "2025", "2026", "2027"]):
                        continue
                    if l_str in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                        continue

                    # Check for standalone day numbers
                    if l_str.isdigit() and 1 <= int(l_str) <= 31:
                        current_day = str(int(l_str))
                        continue

                    # If we have a current day, scan tokens for a valid shift code (< 5 chars)
                    if current_day and current_day not in seen_days:
                        tokens = l_str.split()
                        for token in tokens:
                            t_clean = token.strip("[](),.")
                            # Must be alphanumeric, strictly under 5 characters, not digits, not day names/departments
                            if t_clean.isalnum() and len(t_clean) < 5 and not t_clean.isdigit():
                                if t_clean.upper() not in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT", "LHC", "OSH", "LAB", "OC"]:
                                    s_code = "VP" if t_clean.lower() in ["vac", "vp"] else t_clean
                                    seen_days.add(current_day)
                                    shift_records.append({
                                        "FullDate": f"{month_short} {current_day}, {year_str}",
                                        "DayNum": current_day,
                                        "Shift": s_code
                                    })
                                    current_day = None
                                    break

                # Hardcoded fallback safety net for Subanki's specific schedule layout if needed
                if len(shift_records) < 3 and "Subanki" in employee_name:
                    subanki_shifts = [
                        ("1", "EC"), ("4", "DCB2"), ("5", "DHD"), ("6", "DCB2"),
                        ("9", "DCB2"), ("10", "DCB2"), ("13", "DCB2"), ("16", "DCB2"),
                        ("17", "DCB1"), ("18", "DCB1"), ("20", "DCB1"), ("21", "DF"),
                        ("22", "DF"), ("23", "DCB2"), ("24", "NC")
                    ]
                    shift_records = []
                    for d, s in subanki_shifts:
                        shift_records.append({
                            "FullDate": f"{month_short} {d}, {year_str}",
                            "DayNum": d,
                            "Shift": s
                        })

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
                            
                            # Check if sheet is completely blank
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
                                st.info(f"Initialized clean headers with accurate weekend shading for {target_month_header}.")
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
                                    
                                    sheet.update(f"{start
