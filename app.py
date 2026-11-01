import streamlit as st
import pdfplumber
import pandas as pd
import gspread

# ---------------------------------------------------------
# CONFIGURATION (Set your credentials and security codes here)
# ---------------------------------------------------------
VALID_USERS = {
    "admin26": "@ellica987",
    "manager": "admin2026"
}
SECRET_ACCESS_CODE = "UKG2026"  # The code they must type to see the link
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
        entered_code = st.text_input("Enter the security code to reveal the schedule link:", type="password")
        
        col_btn1, col_btn2, col_btn3 = st.columns([2.3, 1, 2.3])
        with col_btn2:
            if st.button("Submit Code"):
                if entered_code == SECRET_ACCESS_CODE:
                    st.session_state["code_unlocked"] = True
                    st.success("Access Granted.")
                    st.rerun()
                else:
                    st.error("Incorrect Access Code. Please try again.")

    else:
        st.success("Access Code Verified.")
        st.markdown(f"### [Click Here to Open Master Google Sheet]({GOOGLE_SHEET_URL})")
        st.write("---")

        # ---------------------------------------------------------
        # SCHEDULE PDF UPLOADER SECTION
        # ---------------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>Upload Shift Schedule PDF</h3>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose a PDF schedule file to import:", type=["pdf"])

        if uploaded_file is not None:
            st.info("File uploaded successfully. Parsing UKG schedule layout...")
            
            try:
                import pdfplumber
                import re
                
                parsed_rows = []
                # Add header row for your Google Sheet
                header = ["Date", "Shift Type", "Time", "Hours", "Notes"]
                parsed_rows.append(header)
                
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            lines = [line.strip() for line in text.split("\n") if line.strip()]
                            
                            # Regex patterns for UKG schedule format
                            date_pattern = re.compile(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})$', re.IGNORECASE)
                            time_pattern = re.compile(r'(\d{2}:\d{2}\s*-\s*\d{2}:\d{2})\s*\[([\d\.]+)\]')
                            
                            current_date = "Unknown"
                            i = 0
                            while i < len(lines):
                                line = lines[i]
                                
                                # Check if line is a date marker (e.g., "Sun 1")
                                date_match = date_pattern.match(line)
                                if date_match:
                                    current_date = f"{date_match.group(1)} {date_match.group(2)}"
                                    i += 1
                                    continue
                                    
                                # Check if line contains shift times and hours
                                time_match = time_pattern.search(line)
                                if time_match:
                                    time_str = time_match.group(1)
                                    hours_str = time_match.group(2)
                                    
                                    # Shift type is usually the line right before the time
                                    shift_type = lines[i-1] if i > 0 else "Shift"
                                    
                                    # Check for any extra notes/swaps on subsequent lines
                                    notes = ""
                                    if i + 1 < len(lines) and not date_pattern.match(lines[i+1]) and not time_pattern.search(lines[i+1]):
                                        notes = lines[i+1]
                                        
                                    parsed_rows.append([current_date, shift_type, time_str, hours_str, notes])
                                i += 1

                # Fallback if structured parsing finds nothing
                if len(parsed_rows) <= 1:
                    parsed_rows = [["Date", "Schedule Details"], ["All", "UKG Layout Parsed"]]

                df_preview = pd.DataFrame(parsed_rows[1:], columns=parsed_rows[0])
                st.write("Preview of Extracted Schedule Data:")
                st.dataframe(df_preview)

                col_sub1, col_sub2, col_sub3 = st.columns([2.3, 1, 2.3])
                with col_sub2:
                    if st.button("Populate Sheet"):
                        try:
                            gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
                            sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                            sheet.clear()
                            sheet.append_rows(parsed_rows)
                            st.success("Schedule successfully pushed to Google Sheet!")
                        except Exception as e:
                            st.error(f"Error connecting to Google Sheets: {e}")
            except Exception as ex:
                st.error(f"Could not parse PDF: {ex}")
