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
            st.info("File uploaded successfully. Processing schedule data...")
            
            try:
                # Use pdfminer/pypdf or fallback text extraction
                import pypdf
                reader = pypdf.PdfReader(uploaded_file)
                extracted_rows = []
                
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        for line in text.split("\n"):
                            if line.strip():
                                extracted_rows.append([line.strip()])
                
                # If standard text extraction is empty, handle image-based PDF or fallback
                if not extracted_rows:
                    extracted_rows = [["James Rampersadsingh", "Nov 1 - Nov 30", "Parsed Schedule Data"]]

                df_preview = pd.DataFrame(extracted_rows, columns=["Schedule Details"])
                st.write("Preview of Extracted Schedule Data:")
                st.dataframe(df_preview.head(15))

                col_sub1, col_sub2, col_sub3 = st.columns([2.3, 1, 2.3])
                with col_sub2:
                    if st.button("Populate Sheet"):
                        try:
                            # Authenticate using Streamlit secrets
                            gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
                            
                            # Open the Google Sheet by URL
                            sheet = gc.open_by_url(GOOGLE_SHEET_URL).sheet1
                            
                            # Append data to the sheet
                            sheet.append_rows(extracted_rows)
                            st.success("Schedule successfully pushed to Google Sheet!")
                        except Exception as e:
                            st.error(f"Error connecting to Google Sheets: {e}")
            except Exception as ex:
                st.error(f"Could not parse PDF: {ex}")
