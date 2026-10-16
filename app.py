import streamlit as st
import time
from datetime import datetime
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


# Dialog Pop-up for Submission Confirmation
@st.dialog("🎉 Submission Received!")
def show_submission_popup(course, tracking_token, timestamp_str):
    st.success("Your course page PDF has been successfully uploaded for QEC review.")
    st.write(f"**Course:** {course}")
    st.write(f"**Tracking Token:** `{tracking_token}`")
    st.write(f"**Submitted On:** {timestamp_str}")
    st.info("You can enter your registered email under 'Track Submission Status' to view reviews and comments.")
    if st.button("Close Window"):
        st.rerun()


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
                    # Folder-safe naming
                    clean_instructor = "".join(c if c.isalnum() else "_" for c in instructor.strip())
                    clean_course = "".join(c if c.isalnum() else "_" for c in course.strip())
                    
                    timestamp_int = int(time.time())
                    tracking_token = f"QEC-{timestamp_int}"
                    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Store inside dynamic subfolders
                    file_path = f"{clean_instructor}/{clean_course}/{timestamp_int}_submission.pdf"
                    
                    file_bytes = pdf.read()
                    
                    # Upload to Supabase Storage Bucket
                    supabase.storage.from_("moellim-pdfs").upload(
                        file_path, 
                        file_bytes, 
                        {"content-type": "application/pdf", "upsert": "true"}
                    )
                    
                    public_url = supabase.storage.from_("moellim-pdfs").get_public_url(file_path)

                    record = {
                        "course_title": course.strip(),
                        "instructor_name": instructor.strip(),
                        "email": email.strip().lower(),
                        "pdf_url": public_url,
                        "status": "Pending Review",
                        "feedback": "Awaiting initial review"
                    }
                    supabase.table("submissions").insert(record).execute()
                    
                    # Trigger Pop-up
                    show_submission_popup(course, tracking_token, timestamp_str)

    # --- TRACK STATUS TAB (GROUPED BY EMAIL) ---
    with tab_track:
        st.header("Track Submission Status")
        search_email = st.text_input("Enter your registered email address:")
        
        if search_email:
            clean_email = search_email.strip().lower()
            response = supabase.table("submissions").select("*").eq("email", clean_email).order("created_at", desc=True).execute()
            data = response.data
            
            if data:
                instructor_name = data[0].get("instructor_name", "Instructor")
                
                st.markdown(f"### 👤 Profile: `{clean_email}`")
                st.caption(f"Showing **{len(data)}** total submission(s) for **{instructor_name}**")
                st.divider()

                # Group Submissions by Course Code/Title
                course_groups = {}
                for item in data:
                    c_title = item.get("course_title", "Uncategorized Course")
                    course_groups.setdefault(c_title, []).append(item)

                # Render Grouped Cards
                for c_title, submissions in course_groups.items():
                    st.subheader(f"📖 {c_title}")
                    
                    for sub in submissions:
                        status = sub.get("status", "Pending Review")
                        
                        if status == "Approved":
                            badge = "✅ Approved"
                        elif status == "Changes Requested":
                            badge = "⚠️ Changes Requested"
                        elif status == "Rejected":
                            badge = "❌ Rejected"
                        else:
                            badge = "⏳ Pending Review"

                        with st.expander(f"Submission #{sub['id']} — {badge}"):
                            st.write(f"**Submitted Date:** {sub['created_at'][:10]}")
                            st.write(f"**Current Status:** {status}")
                            st.write(f"**Reviewer Feedback:** {sub['feedback']}")
                            if sub.get('pdf_url'):
                                st.markdown(f"[📄 View/Download Uploaded PDF]({sub['pdf_url']})")
                    
                    st.write("") 
            else:
                st.info("No course submissions found associated with this email address.")

# ==========================================
# 2. EVALUATOR / ADMIN PORTAL (PROTECTED - EMAIL GROUPED)
# ==========================================
elif role == "Evaluator (Admin) Portal":
    st.title("QEC Evaluator Portal")

    # Password Authentication Gate
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

        st.subheader("Manage & Grade Submissions (Grouped by Email)")

        # Fetch all submissions ordered by newest first
        res = supabase.table("submissions").select("*").order("created_at", desc=True).execute()
        rows = res.data

        if rows:
            # Group submissions strictly by Email
            email_groups = {}
            for row in rows:
                instructor_email = row.get("email", "no-email@provided.com").strip().lower()
                email_groups.setdefault(instructor_email, []).append(row)

            st.write(f"Total Active Instructors: **{len(email_groups)}** | Total Submissions: **{len(rows)}**")
            st.divider()

            status_options = ["Pending Review", "Approved", "Changes Requested", "Rejected"]

            # Loop through each instructor email group
            for email_addr, submissions in email_groups.items():
                instructor_name = submissions[0].get("instructor_name", "Instructor")
                
                with st.expander(f"📧 {email_addr} — ({instructor_name}) | [{len(submissions)} Submission(s)]"):
                    for row in submissions:
                        st.markdown(f"#### 📖 Course: `{row['course_title']}`")
                        st.write(f"**Submitted Date:** {row['created_at'][:10]}")
                        st.write(f"**Current Status:** `{row.get('status', 'Pending Review')}`")
                        st.markdown(f"[📄 Download/View PDF]({row['pdf_url']})")

                        current_status = row.get("status", "Pending Review")
                        default_index = status_options.index(current_status) if current_status in status_options else 0

                        with st.form(f"eval_form_{row['id']}"):
                            new_status = st.selectbox("Update Status", status_options, index=default_index)
                            new_feedback = st.text_area("Review Comments / Feedback", value=row.get("feedback", ""))
                            
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                if st.form_submit_button("Save & Update"):
                                    supabase.table("submissions").update({
                                        "status": new_status,
                                        "feedback": new_feedback
                                    }).eq("id", row["id"]).execute()
                                    st.success(f"Updated status for {row['course_title']}!")
                                    st.rerun()
                            with col2:
                                if st.form_submit_button("🗑️ Delete Record"):
                                    supabase.table("submissions").delete().eq("id", row["id"]).execute()
                                    st.warning("Submission deleted.")
                                    st.rerun()
                        st.markdown("---")
        else:
            st.info("No course page submissions found in database.")