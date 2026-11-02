import streamlit as st
import pandas as pd
import gspread
import json
import traceback
from calendar import monthrange
from datetime import datetime
from pypdf import PdfReader
import re

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
                reader = PdfReader(uploaded_file)
                full_text = ""
                extracted_elements = []
                for page in reader.pages:
                    def visitor(text, cm, tm, fontDict, fontSize):
                        if text.strip():
                            extracted_elements.append({
                                "text": text.strip(),
                                "x": tm[4],
                                "y": tm[5]
                            })
                    page.extract_text(visitor_text=visitor)
                    ext = page.extract_text()
                    if ext:
                        full_text += ext + "\n"

                # 1. Dynamic Employee Name Extraction
                name_match = re.search(r'(?:JR|SJ|AM|MK|JS|DB|Employee|Name|Schedule for)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', full_text)
                if name_match:
                    extracted_candidate = name_match.group(1).strip()
                else:
                    lines = full_text.split('\n')
                    extracted_candidate = "Team Member"
                    for line
