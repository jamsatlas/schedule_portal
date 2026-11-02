import streamlit as st
import pandas as pd
import gspread
import json
import traceback
from calendar import monthrange
from datetime import datetime
from pypdf import PdfReader
import re

VALID_USERS = {
    "admin26": "@ellica987",
    "manager": "admin2026"
}
SECRET_ACCESS_CODE = "UKG2026"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1JP988S0UxEe6yLNwb5qxE2Pb47FgQCiCfbvIsW_qC7Q/edit?usp=sharing"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "code_unlocked" not in st.session_state:
    st.session_state["code_unlocked"] = False

st.set_page_config(page_title="Team Schedule Portal", layout="centered")

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
        st.markdown("<h3 style='text-align: center;'>Upload Individual UKG Schedule PDF</h3>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose your individual schedule PDF:", type=["pdf"])
        if uploaded_file is not None:
            st.info("Reading PDF schedule layout and extracting shifts universally...")
            try:
                reader = PdfReader(uploaded_file)
                full_text = ""
                extracted_elements = []
                for page in reader.pages:
                    def visitor(text, cm, tm, fontDict, fontSize):
                        if text.strip():
                            extracted_elements.append({
                                "text": text.strip(),
                                "x": tm[4],
                                "y": tm[5]
                            })
                    page.extract_text(visitor_text=visitor)
                    ext = page.extract_text()
                    if ext:
                        full_text += ext + "\n"

                # 1. Dynamic Employee Name Extraction
                name_match = re.search(r'(?:JR|SJ|AM|MK|JS|DB|Employee|Name|Schedule for)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', full_text)
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

                # 2. Month & Year Parser
                month_name = "November"
                year_str = "2026"
                date_range_match = re.search(r'(\d{4})-(\d{2})-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}', full_text)
                if date_range_match:
                    year_str = date_range_match.group(1)
                    month_num = int(date_range_match.group(2))
                    month_name = datetime(2026, month_num, 1).strftime('%B')
                month_short = month_name[:3]

                # 3. Dynamic Text-Proximity Shift Extraction
                days_detected = []
                for el in extracted_elements:
                    t = el["text"]
                    if t.isdigit() and 1 <= int(t) <= 31:
                        if el["y"] > 90:
                            days_detected.append(el)

                sorted_elements = sorted(extracted_elements, key=lambda e: e["y"])
                shift_records = []
                seen_days = set()

                for d in sorted(days_detected, key=lambda d: d["y"]):
                    day_num = int(d["text"])
                    if day_num in seen_days:
                        continue
                    
                    dy = d["y"]
                    dx = d["x"]
                    
                    candidate_shifts = []
                    for other in sorted_elements:
                        sy = other["y"]
                        sx = other["x"]
                        if 0 < (sy - dy) <= 75 and abs(sx - dx) < 600:
                            txt = other["text"].strip()
                            if not re.match(r'^\d{2}:\d{2}', txt) and not any(noise in txt.lower() for noise in ["lhc", "osh", "lab", "technologist", "swap", "opseu", "remembrance", "0714", "0715"]):
                                candidate_shifts.append((sy, txt))

                    if candidate_shifts:
                        candidate_shifts.sort(key=lambda item: item[0])
                        s_code = candidate_shifts[0][1]
                        seen_days.add(day_num)
                        shift_records.append({
                            "FullDate": f"{month_short} {day_num}, {year_str}",
                            "DayNum": str(day_num),
                            "Shift": "VP" if any(v in s_code.upper() for v in ["VAC", "VP"]) else s_code
                        })

                shift_records = sorted(shift_records, key=lambda x: int(x["DayNum"]))

                # 4. Preview & Sync
                st.success(f"Detected Employee: **{employee_name}** | Schedule Period: **{month_name} {year_str}**")
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)[["FullDate", "Shift"]]
                    df_extracted.columns = ["Date", "Shift"]
                    st.write(f"Extracted Shifts Preview ({month_name} {year_str}):")
                    st.dataframe(df_extracted, hide_index=True)

                    if st.button("Sync to Google Sheet"):
                        try:
                            raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
                            cred_dict = json.loads(raw_secret) if isinstance(raw_secret, str) else dict(raw_secret)
                            if "private_key" in cred_dict:
                                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n").replace("\n", "\n")
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
                            for record in shift_records:
                                target_day = record["DayNum"]
                                matched_col_idx = None
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
                            st.error(f"Google Sheets sync error:\n{traceback.format_exc()}")
                else:
                    st.warning("No shift entries detected in this PDF schedule.")
            except Exception as ex:
                st.error(f"Error processing PDF: {traceback.format_exc()}")
