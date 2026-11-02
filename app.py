import streamlit as st
import pandas as pd
import gspread
import json
import traceback
from calendar import monthrange
from datetime import datetime
from pypdf import PdfReader
import re
import io

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
                # We will import the robust parsing logic from schedule_parser.py
                import schedule_parser
                
                # Parse the PDF using Claude's robust modular parser
                pdf_bytes = uploaded_file.getvalue()
                parsed_data = schedule_parser.parse_schedule(pdf_bytes)
                
                employee_name = st.text_input("Confirm or edit detected employee full name:", value=parsed_data.get("name", "Team Member"))
                start_date = parsed_data.get("start")
                
                if not start_date:
                    st.error("Could not find schedule date range in PDF.")
                    st.stop()
                    
                month_name = start_date.strftime("%B")
                year_str = str(start_date.year)
                
                # Convert parsed shift dictionary to records matching UI format
                shift_records = []
                for s in parsed_data.get("shifts", []):
                    shift_records.append({
                        "FullDate": s["date"].strftime("%b %d, %Y"),
                        "DayNum": str(s["date"].day),
                        "Shift": s["code"]
                    })
                
                # 4. Preview & Sync
                st.success(f"Detected Employee: **{employee_name}** | Schedule Period: **{month_name} {year_str}**")
                if shift_records:
                    df_extracted = pd.DataFrame(shift_records)[["FullDate", "Shift"]]
                    df_extracted.columns = ["Date", "Shift"]
                    st.write(f"Extracted Shifts Preview ({month_name} {year_str}) — Holidays Excluded:")
                    st.dataframe(df_extracted, hide_index=True)

                    if st.button("Sync to Google Sheet"):
                        try:
                            raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
                            cred_dict = json.loads(raw_secret) if isinstance(raw_secret, str) else dict(raw_secret)
                            if "private_key" in cred_dict:
                                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                            
                            gc = gspread.service_account_from_dict(cred_dict)
                            sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                            data = sheet.get_all_values()
                            
                            target_month_header = f"{month_name} {year_str}"
                            month_int = start_date.month
                            num_days = monthrange(start_date.year, month_int)[1]

                            # 1. Initialize sheet if completely empty
                            if len(data) < 2:
                                sheet.update("A1:A2", [[""], ["Employee Name"]])
                                data = sheet.get_all_values()
                                
                            row1_month = data[0]
                            row2_days = data[1] if len(data) > 1 else []
                            
                            # 2. Find exact starting column for this month
                            month_start_col = -1
                            for col_idx, header in enumerate(row1_month):
                                if target_month_header.lower() in header.lower():
                                    month_start_col = col_idx
                                    break
                                    
                            if month_start_col == -1:
                                # Month doesn't exist, strictly append it to the right of the last recorded day
                                last_day_col = 0
                                for i, val in enumerate(row2_days):
                                    if val.strip() != "":
                                        last_day_col = i
                                        
                                month_start_col = max(1, last_day_col + 1)
                                
                                # Write Month Header
                                sheet.update(gspread.utils.rowcol_to_a1(1, month_start_col + 1), [[target_month_header]])
                                
                                # Write Day Numbers (1 to 30/31)
                                days_list = [str(d) for d in range(1, num_days + 1)]
                                sheet.update(gspread.utils.rowcol_to_a1(2, month_start_col + 1), [days_list])
                                
                                # Refresh data
                                data = sheet.get_all_values()
                                row2_days = data[1]

                            # 3. Ensure employee row exists
                            emp_row_idx = -1
                            target_row_data = []
                            for idx in range(2, len(data)):
                                row = data[idx]
                                if len(row) > 0 and employee_name.lower() in row[0].lower():
                                    emp_row_idx = idx
                                    target_row_data = list(row)
                                    break

                            if emp_row_idx == -1:
                                # Add new employee
                                emp_row_idx = len(data)
                                target_row_data = [employee_name]
                                sheet.update(f"A{emp_row_idx + 1}", [[employee_name]])

                            # Pad in-memory row up to the end of this month's columns
                            end_col = month_start_col + num_days
                            while len(target_row_data) < end_col:
                                target_row_data.append("")

                            # 4. Map shifts PRECISELY to this month's isolated columns
                            updates_count = 0
                            for record in shift_records:
                                target_day = record["DayNum"]
                                matched_col_idx = -1
                                
                                for col_idx in range(month_start_col, end_col):
                                    if col_idx < len(row2_days) and row2_days[col_idx].strip() == target_day:
                                        matched_col_idx = col_idx
                                        break
                                        
                                if matched_col_idx != -1:
                                    target_row_data[matched_col_idx] = record["Shift"]
                                    updates_count += 1

                            # 5. ISOLATED WRITE: Only update the exact slice for this month. 
                            # This guarantees October's data (to the left) is completely untouched!
                            slice_to_write = target_row_data[month_start_col:end_col]
                            start_a1 = gspread.utils.rowcol_to_a1(emp_row_idx + 1, month_start_col + 1)
                            
                            sheet.update(start_a1, [slice_to_write])
                            st.success(f"Successfully updated {updates_count} shifts for {employee_name} in Master Sheet!")
                        except Exception as sheet_err:
                            st.error(f"Google Sheets sync error:\n{traceback.format_exc()}")
                else:
                    st.warning("No shift entries detected in this PDF schedule.")
            except Exception as ex:
                st.error(f"Error processing PDF: {traceback.format_exc()}")
