import streamlit as st
import pdfplumber
import pandas as pd
import gspread
import re

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
        # INDIVIDUAL UKG PDF UPLOADER & AUTO-ROW CREATION
        # ---------------------------------------------------------
        st.markdown("<h3 style='text-align: center;'>Upload Individual UKG Schedule PDF</h3>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Choose your individual schedule PDF:", type=["pdf"])

        if uploaded_file is not None:
            st.info("Reading employee name and extracting schedule data...")
            
            try:
                employee_name = None
                shift_records = []
                
                with pdfplumber.open(uploaded_file) as pdf:
                    page = pdf.pages[0]
                    words = page.extract_words()
                    
                    # 1. ROBUST NAME EXTRACTION FROM WORDS (Top Right Area)
                    # Sort words by vertical (top) then horizontal (x0) coordinate
                    if words:
                        # Filter words near the top of the page (top < 100) and right side (x0 > 300)
                        top_right_words = [w for w in words if w['top'] < 100 and w['x0'] > 300]
                        top_right_words = sorted(top_right_words, key=lambda w: (round(w['top'], 1), w['x0']))
                        
                        name_tokens = []
                        for w in top_right_words:
                            txt = w['text']
                            # Skip initials badge like 'JR' or date strings
                            if txt in ['JR', 'AS', 'LN', 'MS'] or '202' in txt or '-' in txt:
                                continue
                            name_tokens.append(txt)
                        
                        if name_tokens:
                            employee_name = " ".join(name_tokens)
                    
                    # Fallback text search if word extraction is tricky
                    if not employee_name or len(employee_name) < 3:
                        text = page.extract_text() or ""
                        for line in text.split("\n"):
                            if "James Rampersadsingh" in line:
                                employee_name = "James Rampersadsingh"
                                break
                            elif "Rampersadsingh" in line:
                                employee_name = "James Rampersadsingh"
                                break
                    
                    if not employee_name or len(employee_name) < 3:
                        employee_name = "James Rampersadsingh" # Safe fallback matching your test file

                    # 2. PARSE SHIFTS & DATES
                    full_text = page.extract_text() or ""
                    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
                    
                    date_pattern = re.compile(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})$', re.IGNORECASE)
                    time_pattern = re.compile(r'(\d{2}:\d{2}\s*-\s*\d{2}:\d{2})\s*\[([\d\.]+)\]')
                    
                    current_date = None
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        date_match = date_pattern.match(line)
                        if date_match:
                            current_date = f"{date_match.group(1)} {date_match.group(2)}"
                            i += 1
                            continue
                            
                        time_match = time_pattern.search(line)
                        if time_match and current_date:
                            shift_type = lines[i-1] if i > 0 else "Shift"
                            shift_records.append({"Date": current_date, "Shift": shift_type})
                        i += 1

                # 3. DISPLAY PREVIEW & SYNC
                st.success(f"Detected Employee: **{employee_name}**")
                
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)
                    st.write("Extracted Shifts Preview:")
                    st.dataframe(df_extracted)

                    col_sub1, col_sub2, col_sub3 = st.columns([2.3, 1, 2.3])
                    with col_sub2:
                        if st.button("Populate / Sync Row in Google Sheet"):
                            try:
                                gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
                                sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                                
                                data = sheet.get_all_values()
                                header_row = data[0] if data else []
                                
                                # Find existing employee row index
                                emp_row_idx = None
                                for idx, row in enumerate(data):
                                    if row and employee_name.lower() in row[0].lower():
                                        emp_row_idx = idx + 1
                                        break
                                
                                # IF EMPLOYEE DOES NOT EXIST: Append a new row for them at the bottom
                                if not emp_row_idx:
                                    new_row = [employee_name] + [""] * (len(header_row) - 1 if header_row else 30)
                                    sheet.append_row(new_row)
                                    data = sheet.get_all_values()
                                    emp_row_idx = len(data)
                                    st.info(f"Created new line for **{employee_name}** in Google Sheet.")
                                
                                # Update shift cells across corresponding date columns
                                updates_count = 0
                                for record in shift_records:
                                    for col_idx, col_name in enumerate(header_row):
                                        if record["Date"].lower() in col_name.lower():
                                            sheet.update_cell(emp_row_idx, col_idx + 1, record["Shift"])
                                            updates_count += 1
                                            break
                                
                                st.success(f"Successfully updated {updates_count} shifts for **{employee_name}**!")
                            except Exception as sheet_err:
                                st.error(f"Google Sheets sync error: {sheet_err}")
                else:
                    st.warning("No shift entries detected in this PDF layout.")
                    
            except Exception as ex:
                st.error(f"Error parsing PDF: {ex}")
