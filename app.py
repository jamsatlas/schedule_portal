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

def parse_existing_sheet(data):
    if len(data) < 2:
        return [], {}
        
    row1 = data[0]
    row2 = data[1]
    
    employees = []
    for r in range(2, len(data)):
        if data[r] and data[r][0].strip():
            emp = data[r][0].strip()
            if emp not in employees:
                employees.append(emp)

    months = {}
    total_cols = len(row2)
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
            
        start_c, title, yr, mo = month_found
        n_days = monthrange(yr, mo)[1]
        
        emp_shifts = {}
        for emp in employees:
            emp_row = None
            for r in range(2, len(data)):
                if data[r] and data[r][0].strip().lower() == emp.lower():
                    emp_row = data[r]
                    break
            
            shifts_list = []
            for d in range(1, n_days + 1):
                col_i = start_c + (d - 1)
                val = ""
                if emp_row and col_i < len(emp_row):
                    val = emp_row[col_i].strip()
                shifts_list.append(val)
            emp_shifts[emp] = shifts_list
            
        months[(yr, mo)] = {
            'title': title,
            'num_days': n_days,
            'employee_shifts': emp_shifts
        }
        c = start_c + n_days
        
    return employees, months

def rebuild_sheet_grid(employees, months):
    sorted_month_keys = sorted(months.keys())
    
    row1 = [""]
    row2 = ["Employee Name"]
    
    for key in sorted_month_keys:
        m_info = months[key]
        n_days = m_info['num_days']
        row1.extend([m_info['title']] + [""] * (n_days - 1))
        row2.extend([str(d) for d in range(1, n_days + 1)])
        
    grid = [row1, row2]
    
    for emp in employees:
        emp_row = [emp]
        for key in sorted_month_keys:
            m_info = months[key]
            emp_shifts = m_info['employee_shifts'].get(emp, [""] * m_info['num_days'])
            emp_row.extend(emp_shifts)
        grid.append(emp_row)
        
    return grid

def apply_full_schedule_formatting(spreadsheet, sheet, data):
    if len(data) < 2:
        return
    
    row1 = data[0]
    row2 = data[1]
    total_cols = len(row2)
    max_rows = max(len(data) + 10, 30)
    
    requests = []

    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet.id,
                "gridProperties": {
                    "frozenRowCount": 2,
                    "frozenColumnCount": 1
                }
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
        }
    })

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
                "startRowIndex": 1,
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

        for d in range(1, n_days + 1):
            col_pos = start_c + (d - 1)
            if col_pos >= total_cols:
                break
            dt = date(yr, mo, d)
            if dt.weekday() in (5, 6):
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet.id,
                            "startRowIndex": 1,
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
        st.markdown("<h3 style='text-align: center;'>Upload UKG Schedule PDFs</h3>", unsafe_allow_html=True)
        
        uploaded_files = st.file_uploader("Choose one or multiple individual schedule PDFs:", type=["pdf"], accept_multiple_files=True)
        
        if uploaded_files:
            st.info(f"Processing {len(uploaded_files)} PDF schedule(s)...")
            import schedule_parser
            
            parsed_batch = []
            
            for idx, file in enumerate(uploaded_files):
                try:
                    pdf_bytes = file.getvalue()
                    parsed = schedule_parser.parse_schedule(pdf_bytes)
                    emp_name = parsed.get("name", f"Employee {idx+1}")
                    start_dt = parsed.get("start")
                    
                    if not start_dt:
                        st.warning(f"Could not find schedule date range in {file.name}. Skipping.")
                        continue
                        
                    shift_recs = []
                    for s in parsed.get("shifts", []):
                        shift_recs.append({
                            "FullDate": s["date"].strftime("%b %d, %Y"),
                            "DayNum": str(s["date"].day),
                            "Shift": s["code"],
                            "Time": s.get("time", "")
                        })
                        
                    parsed_batch.append({
                        "file_id": f"file_{idx}",
                        "filename": file.name,
                        "employee_name": emp_name,
                        "start_date": start_dt,
                        "month_name": start_dt.strftime("%B"),
                        "year_str": str(start_dt.year),
                        "shift_records": shift_recs
                    })
                except Exception as parse_err:
                    st.error(f"Error parsing {file.name}: {parse_err}")

            if parsed_batch:
                st.success(f"Successfully extracted {len(parsed_batch)} schedule(s)! Review each schedule table below:")
                
                edited_batch = []
                
                for item in parsed_batch:
                    exp_title = f"📋 {item['employee_name']} — {item['month_name']} {item['year_str']} ({item['filename']})"
                    with st.expander(exp_title, expanded=True):
                        emp_name_edited = st.text_input(
                            f"Employee Name ({item['filename']}):",
                            value=item["employee_name"],
                            key=f"name_{item['file_id']}"
                        )
                        
                        df_shifts = pd.DataFrame(item["shift_records"])
                        df_shifts = df_shifts[["FullDate", "DayNum", "Shift", "Time"]]
                        df_shifts.columns = ["Date", "Day", "Shift Code", "Time Range"]
                        
                        st.markdown("**Shift Breakdown (Double-click any Shift Code cell to edit if needed):**")
                        edited_df = st.data_editor(
                            df_shifts,
                            key=f"editor_{item['file_id']}",
                            hide_index=True,
                            use_container_width=True
                        )
                        
                        reconstructed_records = []
                        for _, row in edited_df.iterrows():
                            reconstructed_records.append({
                                "FullDate": row["Date"],
                                "DayNum": str(row["Day"]),
                                "Shift": str(row["Shift Code"]).strip()
                            })
                            
                        edited_batch.append({
                            "employee_name": emp_name_edited.strip(),
                            "start_date": item["start_date"],
                            "month_name": item["month_name"],
                            "year_str": item["year_str"],
                            "shift_records": reconstructed_records
                        })

                st.write("---")
                if st.button("Sync All Schedules to Master Google Sheet", type="primary", use_container_width=True):
                    try:
                        raw_secret = st.secrets["GOOGLE_CREDENTIALS_JSON"]
                        cred_dict = json.loads(raw_secret) if isinstance(raw_secret, str) else dict(raw_secret)
                        if "private_key" in cred_dict:
                            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                        
                        gc = gspread.service_account_from_dict(cred_dict)
                        spreadsheet = gc.open_by_url(GOOGLE_SHEET_URL)
                        
                        by_year = {}
                        for item in edited_batch:
                            yr = item["year_str"]
                            if yr not in by_year:
                                by_year[yr] = []
                            by_year[yr].append(item)
                            
                        for year_tab_name, items in by_year.items():
                            try:
                                sheet = spreadsheet.worksheet(year_tab_name)
                            except Exception:
                                sheet = spreadsheet.add_worksheet(title=year_tab_name, rows=100, cols=400)
                            
                            raw_data = sheet.get_all_values()
                            employees, months_dict = parse_existing_sheet(raw_data)
                            
                            for item in items:
                                emp_name = item["employee_name"]
                                start_dt = item["start_date"]
                                m_name = item["month_name"]
                                y_str = item["year_str"]
                                shift_recs = item["shift_records"]
                                
                                if emp_name not in employees:
                                    employees.append(emp_name)
                                    
                                current_year = start_dt.year
                                current_month = start_dt.month
                                month_key = (current_year, current_month)
                                target_month_title = f"{m_name} {y_str}"
                                num_days = monthrange(current_year, current_month)[1]
                                
                                if month_key not in months_dict:
                                    months_dict[month_key] = {
                                        'title': target_month_title,
                                        'num_days': num_days,
                                        'employee_shifts': {}
                                    }
                                
                                shifts_array = months_dict[month_key]['employee_shifts'].get(emp_name, [""] * num_days)
                                for rec in shift_recs:
                                    d_idx = int(rec["DayNum"]) - 1
                                    if 0 <= d_idx < num_days:
                                        shifts_array[d_idx] = rec["Shift"]
                                        
                                months_dict[month_key]['employee_shifts'][emp_name] = shifts_array
                                
                            for emp in employees:
                                for mk in months_dict:
                                    if emp not in months_dict[mk]['employee_shifts']:
                                        months_dict[mk]['employee_shifts'][emp] = [""] * months_dict[mk]['num_days']
                                        
                            new_grid = rebuild_sheet_grid(employees, months_dict)
                            
                            required_cols = len(new_grid[0])
                            if sheet.col_count < required_cols:
                                sheet.add_cols(required_cols - sheet.col_count)
                            
                            sheet.clear()
                            sheet.update("A1", new_grid)
                            apply_full_schedule_formatting(spreadsheet, sheet, new_grid)

                        st.success(f"Successfully synced all {len(edited_batch)} schedule(s) to Master Sheet!")
                    except Exception as sheet_err:
                        st.error(f"Google Sheets sync error:\n{traceback.format_exc()}")
