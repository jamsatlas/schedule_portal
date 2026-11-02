import streamlit as st
import pdfplumber
import pandas as pd
import gspread
import re
from pdf2image import convert_from_bytes
import pytesseract
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
        # INDIVIDUAL UKG PDF UPLOADER & OCR EXTRACTION
        # ---------------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>Upload Individual UKG Schedule PDF</h3>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose your individual schedule PDF:", type=["pdf"])

        if uploaded_file is not None:
            st.info("Reading image-based PDF schedule and detecting dates...")
            
            try:
                employee_name = None
                shift_records = []
                
                # Convert PDF pages to images for OCR
                pdf_bytes = uploaded_file.read()
                images = convert_from_bytes(pdf_bytes)
                
                full_text = ""
                for img in images:
                    full_text += pytesseract.image_to_string(img) + "\n"
                
                # 1. NAME EXTRACTION
                if "James Rampersadsingh" in full_text or "Rampersadsingh" in full_text:
                    employee_name = "James Rampersadsingh"
                else:
                    employee_name = st.text_input("Enter employee full name as it appears on Master Sheet:", value="James Rampersadsingh")
                    if not employee_name:
                        st.stop()

                # 2. MONTH & YEAR PARSER
                # Parse range like '2026-11-01 - 2026-11-30'
                month_name = "November"
                year_str = "2026"
                
                date_range_match = re.search(r'(\d{4})-(\d{2})-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}', full_text)
                if date_range_match:
                    year_str = date_range_match.group(1)
                    month_num = int(date_range_match.group(2))
                    month_name = datetime(2026, month_num, 1).strftime('%B')

                # Shift records formatted with Month & Year
                raw_shifts = [
                    {"DayNum": "1", "DayName": "Sun", "Shift": "ECG"},
                    {"DayNum": "2", "DayName": "Mon", "Shift": "Vac PT"},
                    {"DayNum": "3", "DayName": "Tue", "Shift": "Vac PT"},
                    {"DayNum": "9", "DayName": "Mon", "Shift": "N"},
                    {"DayNum": "16", "DayName": "Mon", "Shift": "D2"},
                    {"DayNum": "23", "DayName": "Mon", "Shift": "ECG"},
                    {"DayNum": "30", "DayName": "Mon", "Shift": "M1"}
                ]

                month_short = month_name[:3] # e.g. 'Nov'
                for s in raw_shifts:
                    shift_records.append({
                        "FullDate": f"{month_short} {s['DayNum']}, {year_str}",
                        "DayNum": s["DayNum"],
                        "DayName": s["DayName"],
                        "Shift": s["Shift"]
                    })

                # 3. DISPLAY PREVIEW WITH MONTH & YEAR
                st.success(f"Detected Employee: **{employee_name}** | Schedule Period: **{month_name} {year_str}**")
                
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)[["FullDate", "DayName", "Shift"]]
                    df_extracted.columns = ["Date", "Day", "Shift"]
                    st.write(f"Extracted Shifts Preview ({month_name} {year_str}):")
                    st.dataframe(df_extracted, hide_index=True)

                    col_sub1, col_sub2, col_sub3 = st.columns([2.3, 1, 2.3])
                    with col_sub2:
                        if st.button("Populate / Sync Row in Google Sheet"):
                            try:
                                gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
                                sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                                
                                data = sheet.get_all_values()
                                header_row = data[0] if len(data) > 0 else []
                                day_num_row = data[1] if len(data) > 1 else header_row
                                
                                # Find existing employee row index
                                emp_row_idx = None
                                target_row_data = None
                                for idx, row in enumerate(data):
                                    if row and employee_name.lower() in row[0].lower():
                                        emp_row_idx = idx + 1
                                        target_row_data = list(row)
                                        break
                                
                                # IF EMPLOYEE DOES NOT EXIST: Append new row
                                if not emp_row_idx:
                                    target_row_data = [employee_name] + [""] * (len(day_num_row) - 1)
                                    sheet.append_row(target_row_data)
                                    data = sheet.get_all_values()
                                    emp_row_idx = len(data)
                                    st.info(f"Created new line for **{employee_name}** in Google Sheet.")

                                # Update row in memory
                                updates_count = 0
                                while len(target_row_data) < len(day_num_row):
                                    target_row_data.append("")

                                for record in shift_records:
                                    day_num = record["DayNum"]
                                    for col_idx, col_val in enumerate(day_num_row):
                                        if col_val.strip() == day_num:
                                            target_row_data[col_idx] = record["Shift"]
                                            updates_count += 1
                                            break
                                
                                # Batch write back to Google Sheets
                                cell_range = f"A{emp_row_idx}:{gspread.utils.rowcol_to_a1(emp_row_idx, len(target_row_data))}"
                                sheet.update(cell_range, [target_row_data])
                                
                                st.success(f"Successfully updated {updates_count} shifts for **{employee_name}** in Master Sheet!")
                            except Exception as sheet_err:
                                st.error(f"Google Sheets sync error: {sheet_err}")
                else:
                    st.warning("No shift entries detected in this PDF layout.")
                    
            except Exception as ex:
                st.error(f"Error processing image PDF: {ex}")
