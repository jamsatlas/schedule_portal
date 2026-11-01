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
            st.info("Reading header for employee name and extracting schedule data...")
            
            try:
                employee_name = None
                shift_records = []  # Stores dicts: {"Date": "...", "Shift": "..."}
                
                with pdfplumber.open(uploaded_file) as pdf:
                    first_page = pdf.pages[0]
                    
                    # 1. TOP-RIGHT NAME EXTRACTION
                    # Crop top 15% of the page across the right half (x > 50% width)
                    width = first_page.width
                    height = first_page.height
                    header_crop = first_page.crop((width * 0.5, 0, width, height * 0.15))
                    header_text = header_crop.extract_text()
                    
                    if header_text:
                        for line in header_text.split("\n"):
                            line_clean = line.strip()
                            # Remove initial avatar badges like "JR", "AS", "LN"
                            line_clean = re.sub(r'^[A-Z]{2}\s+', '', line_clean).strip()
                            if len(line_clean) > 2 and not line_clean.startswith("202"):
                                employee_name = line_clean
                                break
                    
                    # Fallback full page text scan if crop returns empty
                    if not employee_name:
                        full_text = first_page.extract_text() or ""
                        for line in full_text.split("\n"):
                            if any(known_name in line for known_name in ["James Rampersadsingh", "Anna Sadowski", "Lidia Nowak"]):
                                employee_name = re.sub(r'^[A-Z]{2}\s+', '', line.strip()).strip()
                                break
                                
                    if not employee_name:
                        employee_name = "Unknown Employee"

                    # 2. PARSE DATES AND SHIFTS
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            
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

                # 3. DISPLAY PREVIEW
                st.success(f"Detected Employee: **{employee_name}**")
                
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)
                    st.write("Extracted Shifts:")
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
                                
                                # IF EMPLOYEE DOES NOT EXIST: Append a new row for them
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
