import streamlit as st
import pdfplumber
import pandas as pd
import gspread
import re
import json
import traceback
from calendar import monthrange
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
            st.info("Running OCR to read image-based PDF schedule and detecting info...")
            
            try:
                employee_name = None
                shift_records = []
                
                pdf_bytes = uploaded_file.read()
                images = convert_from_bytes(pdf_bytes)
                
                full_text = ""
                for img in images:
                    full_text += pytesseract.image_to_string(img) + "\n"
                
                # 1. DYNAMIC NAME EXTRACTION
                name_match = re.search(r'(?:Employee|Name|Schedule for)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', full_text)
                if name_match:
                    extracted_candidate = name_match.group(1).strip()
                    employee_name = st.text_input("Confirm or edit detected employee full name:", value=extracted_candidate)
                else:
                    employee_name = st.text_input("Enter employee full name as it appears on Master Sheet:")
                    if not employee_name:
                        st.warning("Please enter an employee name to continue.")
                        st.stop()

                # 2. MONTH & YEAR PARSER
                month_name = "November"
                year_str = "2026"
                
                date_range_match = re.search(r'(\d{4})-(\d{2})-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}', full_text)
                if date_range_match:
                    year_str = date_range_match.group(1)
                    month_num = int(date_range_match.group(2))
                    month_name = datetime(2026, month_num, 1).strftime('%B')

                # 3. OPEN SHIFT PARSING (ACCEPTS ALL SHIFT NAMES, SKIPS STAT HOLIDAYS)
                lines = full_text.split('\n')
                month_short = month_name[:3]
                seen_days = set()

                for line in lines:
                    line_clean = line.strip()
                    
                    if any(holiday_word in line_clean.lower() for holiday_word in ["remembrance", "holiday", "stat", "flag", "family day", "victoria day", "canada day", "civic", "labour", "thanksgiving", "christmas", "boxing"]):
                        continue
                        
                    match = re.search(r'\b(0?[1-9]|[12]\d|3[01])\b\s+(.*)', line_clean)
                    if match:
                        day_num = str(int(match.group(1)))
                        shift_text = match.group(2).strip()
                        
                        shift_text = re.sub(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s*', '', shift_text, flags=re.IGNORECASE)
                        shift_text = shift_text.strip()
                        
                        if shift_text and not shift_text.isdigit() and day_num not in seen_days:
                            seen_days.add(day_num)
                            shift_code = "VP" if "Vac" in shift_text else shift_text
                            
                            shift_records.append({
                                "FullDate": f"{month_short} {day_num}, {year_str}",
                                "DayNum": day_num,
                                "Shift": shift_code
                            })

                # 4. DISPLAY PREVIEW WITH MONTH & YEAR
                st
