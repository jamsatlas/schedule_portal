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
                            "left": {"style": "SOLID", "width": 1, "color": {"red": 0.7, "green": 0.7,
