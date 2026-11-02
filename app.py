import streamlit as st
import pandas as pd
import gspread
import json
import traceback
from calendar import monthrange
from datetime import datetime, date
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

def apply_full_schedule_formatting(spreadsheet, sheet, data):
    """
    Applies exact grid borders, compact cell widths, centered alignment,
    and calendar-accurate weekend grey shading for all months present in row 1.
    """
    if len(data) < 2:
        return
    
    row1 = data[0]
    row2 = data[1]
    total_cols = len(row2)
    max_rows = max(len(data) + 10, 30)
    
    requests = []

    # 1. Format Column A (Employee Name)
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet.id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 1
            },
            "properties": {"pixelSize": 180},
            "fields": "pixelSize"
        }
    })
    
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet.id,
                "startRowIndex": 1, # Row 2 (Employee Name header)
                "endRowIndex": max_rows,
                "startColumnIndex": 0,
                "endColumnIndex": 1
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "LEFT",
                    "verticalAlignment": "MIDDLE",
                    "borders": {
                        "top": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                        "bottom": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                        "left": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                        "right": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}}
                    }
                }
            },
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,borders)"
        }
    })

    # 2. Identify and format all month blocks in row 1
    c = 1
    while c < total_cols:
        month_found = None
        for col_idx in range(c, total_cols):
            val = row1[col_idx].strip() if col_idx < len(row1) else ""
            if val:
                try:
                    parts = val.split()
                    if len(parts) >= 2:
                        m_str, y_str = parts[0], parts[1]
                        m_int = datetime.strptime(m_str, "%B").month
                        y_int = int(y_str)
                        month_found = (col_idx, val, y_int, m_int)
                        break
                except Exception:
                    pass

        if not month_found:
            break

        start_c, month_title, yr, mo = month_found
        n_days = monthrange(yr, mo)[1]
        end_c = min(start_c + n_days, total_cols)

        # A. Set Day Column Widths (38px compact size)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet.id,
                    "dimension": "COLUMNS",
                    "startIndex": start_c,
                    "endIndex": end_c
                },
                "properties": {"pixelSize": 38},
                "fields": "pixelSize"
            }
        })

        # B. Set base formatting for all day columns (white background, center alignment, grid borders)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": max_rows,
                    "startColumnIndex": start_c,
                    "endColumnIndex": end_c
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "borders": {
                            "top": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                            "bottom": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                            "left": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}},
                            "right": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7, "blue": 0.7}}
                        }
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,borders)"
            }
        })

        # C. Format Month Title (Row 1)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": start_c,
                    "endColumnIndex": start_c + 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 11},
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # D. Format Row 2 (Day Numbers Header)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": start_c,
                    "endColumnIndex": end_c
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # E. Apply Grey Background (#d9d9d9) ONLY to actual Calendar Weekends (Saturday & Sunday)
        for d in range(1, n_days + 1):
            col_pos = start_c + (d - 1)
            if col_pos >= total_cols:
                break
            dt = date(yr, mo, d)
            if dt.weekday() in (5, 6): # 5=Sat, 6=Sun
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet.id,
                            "startRowIndex": 1, # From day numbers row downwards
                            "endRowIndex": max_rows,
                            "startColumnIndex": col_pos,
                            "endColumnIndex": col_pos + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor"
                    }
                })

        c = end_c

    if requests:
        spreadsheet.batch_update({"requests": requests})

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
                import schedule_parser
                
                pdf_bytes = uploaded_file.getvalue()
                parsed_data = schedule_parser.parse_schedule(pdf_bytes)
                
                employee_name = st.text_input("Confirm or edit detected employee full name:", value=parsed_data.get("name", "Team Member"))
                start_date = parsed_data.get("start")
                
                if not start_date:
                    st.error("Could not find schedule date range in PDF.")
                    st.stop()
                    
                month_name = start_date.strftime("%B")
                year_str = str(start_date.year)
                
                shift_records = []
                for s in parsed_data.get("shifts", []):
                    shift_records.append({
                        "FullDate": s["date"].strftime("%b %d, %Y"),
                        "DayNum": str(s["date"].day),
                        "Shift": s["code"]
                    })
                
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
                            spreadsheet = gc.open_by_url(GOOGLE_SHEET_URL)
                            sheet = spreadsheet.sheet1
                            data = sheet.get_all_values()
                            
                            target_month_header = f"{month_name} {year_str}"
                            month_int = start_date.month
                            num_days = monthrange(start_date.year, month_int)[1]

                            if len(data) < 2:
                                sheet.update("A1:A2", [[""], ["Employee Name"]])
                                data = sheet.get_all_values()
                                
                            row1_month = data[0]
                            row2_days = data[1] if len(data) > 1 else []
                            
                            month_start_col = -1
                            for col_idx, header in enumerate(row1_month):
                                if target_month_header.lower() in header.lower():
                                    month_start_col = col_idx
                                    break
                                    
                            if month_start_col == -1:
                                last_day_col = 0
                                for i, val in enumerate(row2_days):
                                    if val.strip() != "":
                                        last_day_col = i
                                        
                                month_start_col = max(1, last_day_col + 1)
                                
                                sheet.update(gspread.utils.rowcol_to_a1(1, month_start_col + 1), [[target_month_header]])
                                days_list = [str(d) for d in range(1, num_days + 1)]
                                sheet.update(gspread.utils.rowcol_to_a1(2, month_start_col + 1), [days_list])
                                
                                data = sheet.get_all_values()
                                row2_days = data[1]

                            emp_row_idx = -1
                            target_row_data = []
                            for idx in range(2, len(data)):
                                row = data[idx]
                                if len(row) > 0 and employee_name.lower() in row[0].lower():
                                    emp_row_idx = idx
                                    target_row_data = list(row)
                                    break

                            if emp_row_idx == -1:
                                emp_row_idx = len(data)
                                target_row_data = [employee_name]
                                sheet.update(f"A{emp_row_idx + 1}", [[employee_name]])

                            end_col = month_start_col + num_days
                            while len(target_row_data) < end_col:
                                target_row_data.append("")

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

                            slice_to_write = target_row_data[month_start_col:end_col]
                            start_a1 = gspread.utils.rowcol_to_a1(emp_row_idx + 1, month_start_col + 1)
                            sheet.update(start_a1, [slice_to_write])
                            
                            # Apply complete formatting (Borders, Cell Sizes, Alignment & Calendar-Accurate Grey Weekend Shading)
                            full_data = sheet.get_all_values()
                            apply_full_schedule_formatting(spreadsheet, sheet, full_data)

                            st.success(f"Successfully updated {updates_count} shifts for {employee_name} in Master Sheet and applied calendar formatting!")
                        except Exception as sheet_err:
                            st.error(f"Google Sheets sync error:\n{traceback.format_exc()}")
                else:
                    st.warning("No shift entries detected in this PDF schedule.")
            except Exception as ex:
                st.error(f"Error processing PDF: {traceback.format_exc()}")
