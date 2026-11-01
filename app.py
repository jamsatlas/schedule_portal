import streamlit as st

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
# STEP 1: USERNAME & PASSWORD LOGIN
# ---------------------------------------------------------
if not st.session_state["authenticated"]:
    st.markdown("<h1 style='text-align: center;'>Team Schedule Portal</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Please Sign In</h3>", unsafe_allow_html=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Adjusted column ratio to align the button flush with the right edge of the inputs
    col1, col2 = st.columns([6.8, 1])
    with col2:
        sign_in_clicked = st.button("Sign In")

    if sign_in_clicked:
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid Username or Password.")

# ---------------------------------------------------------
# STEP 2 & 3: ACCESS CODE GATE & LINK REVEAL
# ---------------------------------------------------------
else:
    st.markdown("<h1 style='text-align: center;'>Welcome to the Schedule Portal</h1>", unsafe_allow_html=True)

    # Center the sign-out button directly underneath the title
    col_out1, col_out2, col_out3 = st.columns([2.3, 1, 2.3])
    with col_out2:
        if st.button("Sign Out"):
            st.session_state["authenticated"] = False
            st.session_state["code_unlocked"] = False
            st.rerun()

    st.write("---")

    # STEP 2: Access Code Gate
    if not st.session_state["code_unlocked"]:
        st.markdown("<h3 style='text-align: center;'>Enter Access Code</h3>", unsafe_allow_html=True)
        entered_code = st.text_input("Enter the security code to reveal the schedule link:", type="password")
        
        # Center the submit button underneath the access code box
        col_btn1, col_btn2, col_btn3 = st.columns([2.3, 1, 2.3])
        with col_btn2:
            submit_clicked = st.button("Submit Code")

        if submit_clicked:
            if entered_code == SECRET_ACCESS_CODE:
                st.session_state["code_unlocked"] = True
                st.success("Access Granted.")
                st.rerun()
            else:
                st.error("Incorrect Access Code. Please try again.")

    # STEP 3: Reveal the Google Sheets link once unlocked
    else:
        st.success("Access Code Verified.")
        st.markdown(f"### [Click Here to Open Master Google Sheet]({GOOGLE_SHEET_URL})")
        st.info("You can bookmark this page or click the link above to view and update your shifts.")