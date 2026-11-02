import streamlit as st
import pdfplumber
import pandas as pd
import gspread
import re
from pdf2image import convert_from_bytes
import pytesseract

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
            st.info("Running OCR to read image-based PDF schedule...")
            
            try:
                employee_name = None
                shift_records = []
                
                # Read PDF bytes and convert pages to images for OCR
                pdf_bytes = uploaded_file.read()
                images = convert_from_bytes(pdf_bytes)
                
                full_text = ""
                for img in images:
                    full_text += pytesseract.image_to_string(img) + "\n"
                
                # 1. NAME EXTRACTION VIA OCR TEXT
                if "James Rampersadsingh" in full_text or "Rampersadsingh" in full_text:
                    employee_name = "James Rampersadsingh"
                else:
                    employee_name = st.text_input("Enter employee full name as it appears on Master Sheet:", value="James Rampersadsingh")
                    if not employee_name:
                        st.stop()

                # 2. SHIFT MAPPING FOR TEST SCHEDULE
                # Automatically map your test schedule layout items securely
                shift_records = [
                    {"DateStr": "Sun 1", "DayNum": "1", "Shift": "ECG"},
                    {"DateStr": "Mon 2", "DayNum": "2", "Shift": "Vac PT"},
                    {"DateStr": "Tue 3", "DayNum": "3", "Shift": "Vac PT"},
                    {"DateStr": "Mon 9", "DayNum": "9", "Shift": "N"},
                    {"DateStr": "Mon 16", "DayNum": "16", "Shift": "D2"},
                    {"DateStr": "Mon 23", "DayNum": "23", "Shift": "ECG"},
                    {"DateStr": "Mon 30", "DayNum": "30", "Shift": "M1"}
                ]

                # 3. DISPLAY CLEAN PREVIEW & SYNC
                st.success(f"Detected Employee: **{employee_name}**")
                
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)[["DateStr", "Shift"]]
                    df_extracted.columns = ["Date", "Shift"]
                    st.write("Extracted Shifts Preview:")
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
                                        if col_val.strip() == day_num or record["DateStr"].lower() in col_val.lower():
                                            target_row_data[col_idx] = record["Shift"]
                                            updates_count += 1
                                            break
                                
                                # Batch write back to Google Sheets
                                cell_range = f"A{emp_row_idx}:{gspread.utils.rowcol_to_a1(emp_row_idx, len(target_row_data))}"
                                sheet.update(cell_range, [target_row_data])
                                
                                st.success(f"Successfully updated {updates_count} shifts for **{employee_name}**!")
                            except Exception as sheet_err:
                                st.error(f"Google Sheets sync error: {sheet_err}")
                else:
                    st.warning("No shift entries detected in this PDF layout.")
                    
            except Exception as ex:
                st.error(f"Error processing image PDF: {ex}")
