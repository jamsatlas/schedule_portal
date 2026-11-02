import json
import traceback
from calendar import monthrange

import gspread
import pandas as pd
import streamlit as st

from schedule_parser import parse_schedule

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


@st.cache_data(show_spinner="Reading schedule (OCR can take a few seconds)...")
def cached_parse(pdf_bytes: bytes):
    return parse_schedule(pdf_bytes)


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
            try:
                result = cached_parse(uploaded_file.getvalue())
                shifts = result["shifts"]
                period_start = result["start"]
                month_name = period_start.strftime("%B")
                year_str = str(period_start.year)

                employee_name = st.text_input(
                    "Confirm or edit detected employee full name:",
                    value=result["name"] or "Team Member",
                )
                st.success(
                    f"Detected Employee: **{employee_name}** | "
                    f"Schedule Period: **{month_name} {year_str}** | "
                    f"Read via: **{result['method']}**"
                )

                if result["method"] == "OCR":
                    st.caption("This PDF is an image, so it was read with OCR. "
                               "Double-check the codes below and fix any mistakes before syncing.")

                if shifts:
                    df = pd.DataFrame({
                        "Date": [f'{s["date"].strftime("%b")} {s["date"].day}, {s["date"].year}' for s in shifts],
                        "Shift": [s["code"] for s in shifts],
                        "Time": [s["time"] for s in shifts],
                    })
                    st.write(f"Extracted Shifts ({month_name} {year_str}) — you can edit the Shift column:")
                    edited = st.data_editor(
                        df, hide_index=True, disabled=["Date", "Time"],
                        num_rows="fixed", use_container_width=True,
                    )
                    if result["skipped"]:
                        with st.expander("Holidays / entries excluded"):
                            for s in result["skipped"]:
                                st.write("• " + s)

                    if st.button("Sync to Google Sheet"):
                        try:
                            # Final records come from the (possibly edited) table
                            shift_records = [
                                {"DayNum": str(shifts[i]["date"].day), "Shift": str(edited.iloc[i]["Shift"]).strip()}
                                for i in range(len(shifts))
                                if str(edited.iloc[i]["Shift"]).strip()
                            ]

                            raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
                            cred_dict = json.loads(raw_secret) if isinstance(raw_secret, str) else dict(raw_secret)
                            if "private_key" in cred_dict:
                                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                            gc = gspread.service_account_from_dict(cred_dict)
                            sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                            data = sheet.get_all_values()
                            target_month_header = f"{month_name} {year_str}"
                            num_days = monthrange(period_start.year, period_start.month)[1]

                            if len(data) < 2 or not data[0] or data[0][0] == "":
                                row1 = ["", target_month_header] + [""] * (num_days - 1)
                                row2 = ["Employee Name"] + [str(d) for d in range(1, num_days + 1)]
                                sheet.update(range_name="A1", values=[row1, row2])
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
                            sheet.update(range_name=cell_range, values=[target_row_data])
                            st.success(f"Successfully updated {updates_count} shifts for {employee_name} in Master Sheet!")
                        except Exception:
                            st.error(f"Google Sheets sync error:\n{traceback.format_exc()}")
                else:
                    st.warning("No shift entries detected in this PDF schedule.")
            except Exception:
                st.error(f"Error processing PDF: {traceback.format_exc()}")
