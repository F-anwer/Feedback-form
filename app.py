import streamlit as st
import time
from supabase import create_client, Client

# Initialize Supabase Client
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Moellim Course Page Review", layout="wide")

# Sidebar Role Selector
st.sidebar.title("Navigation")
role = st.sidebar.radio("Select View:", ["Instructor Portal", "Evaluator (Admin) Portal"])

# ==========================================
# 1. INSTRUCTOR PORTAL (PUBLIC)
# ==========================================
if role == "Instructor Portal":
    st.title("Moellim Course Page Portal")
    
    tab_submit, tab_track = st.tabs(["Submit Course Page", "Track Submission Status"])

    # --- SUBMIT TAB ---
    with tab_submit:
        st.header("Submit Course Page for QEC Review")
        with st.form("faculty_submission", clear_on_submit=True):
            course = st.text_input("Course Title & Code *")
            instructor = st.text_input("Instructor Name *")
            email = st.text_input("Instructor Email *")
            pdf = st.file_uploader("Upload Moellim Page PDF *", type=["pdf"])

            submitted = st.form_submit_button("Submit")
            if submitted:
                if not course or not instructor or not email or not pdf:
                    st.error("Please fill in all required fields and upload your PDF.")
                elif pdf.size > 25 * 1024 * 1024:
                    st.error("File size exceeds 25MB limit.")
                else:
                    timestamp = int(time.time())
                    clean_course = "".join(c if c.isalnum() else "_" for c in course)
                    clean_name = f"{timestamp}_{clean_course}.pdf"
                    
                    file_bytes = pdf.read()
                    
                    # Upload to Supabase Storage Bucket
                    supabase.storage.from_("moellim-pdfs").upload(
                        clean_name, 
                        file_bytes, 
                        {"content-type": "application/pdf", "upsert": "true"}
                    )
                    
                    public_url = supabase.storage.from_("moellim-pdfs").get_public_url(clean_name)

                    record = {
                        "course_title": course,
                        "instructor_name": instructor,
                        "email": email,
                        "pdf_url": public_url,
                        "status": "Pending Review",
                        "feedback": "Awaiting initial review"
                    }
                    supabase.table("submissions").insert(record).execute()
                    st.success(f"Successfully submitted feedback form for {course}!")

    # --- TRACK STATUS TAB ---
    with tab_track:
        st.header("Track Your Submission Status")
        search_email = st.text_input("Enter your registered email to view feedback:")
        
        if search_email:
            response = supabase.table("submissions").select("*").eq("email", search_email.strip()).execute()
            data = response.data
            
            if data:
                st.write(f"Found **{len(data)}** submission(s) for `{search_email}`:")
                for item in data:
                    with st.expander(f"📚 {item['course_title']} — Status: **{item['status']}**"):
                        st.write(f"**Submitted Date:** {item['created_at'][:10]}")
                        st.write(f"**Feedback / Comments:** {item['feedback']}")
                        if item.get('pdf_url'):
                            st.markdown(f"[📄 View Uploaded Document]({item['pdf_url']})")
            else:
                st.info("No submissions found under this email address.")

# ==========================================
# 2. EVALUATOR / ADMIN PORTAL (PROTECTED)
# ==========================================
elif role == "Evaluator (Admin) Portal":
    st.title("QEC Evaluator Portal")

    # Simple Password Gate
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        pwd_input = st.text_input("Enter Admin Password:", type="password")
        if st.button("Login"):
            if pwd_input == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect Password.")
    else:
        if st.sidebar.button("Logout Admin"):
            st.session_state.authenticated = False
            st.rerun()

        st.subheader("Manage & Grade Submissions")
        
        # Retrieve all submissions
        res = supabase.table("submissions").select("*").order("created_at", desc=True).execute()
        rows = res.data

        if rows:
            for row in rows:
                with st.expander(f"Review: {row['course_title']} (Instructor: {row['instructor_name']})"):
                    st.write(f"**Email:** {row['email']}")
                    st.write(f"**Current Status:** {row['status']}")
                    st.markdown(f"[📄 Download/View PDF]({row['pdf_url']})")

                    with st.form(f"review_form_{row['id']}"):
                        new_status = st.selectbox(
                            "Update Status", 
                            ["Pending Review", "Approved", "Changes Requested", "Rejected"],
                            index=["Pending Review", "Approved", "Changes Requested", "Rejected"].index(row.get("status", "Pending Review"))
                        )
                        new_feedback = st.text_area("Review Comments / Feedback", value=row.get("feedback", ""))
                        
                        if st.form_submit_button("Save & Send Review"):
                            supabase.table("submissions").update({
                                "status": new_status,
                                "feedback": new_feedback
                            }).eq("id", row["id"]).execute()
                            
                            st.success(f"Updated status for {row['course_title']}!")
                            st.rerun()
        else:
            st.info("No course page submissions found.")