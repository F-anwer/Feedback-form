import streamlit as st
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client
import time

# Load secrets
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = st.secrets["SMTP_EMAIL"]
SENDER_PASSWORD = st.secrets["SMTP_PASSWORD"]

def send_review_email(recipient_email, instructor_name, course_title, status, feedback):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = recipient_email
        msg["Subject"] = f"Moellim Review Outcome: {course_title} - {status}"

        instructions = ""
        if status == "Needs revision":
            instructions = "Please revise the missing items according to the checklist and re-upload your page."
        elif status == "Approved with changes":
            instructions = "Please make the minor updates noted on your Moellim page."
        else:
            instructions = "Your course page meets all checklist requirements. No further action is required."

        body = f"Dear {instructor_name},\n\nYour Moellim course page review for {course_title} has been completed.\n\nStatus: {status}\n\nReviewer Feedback:\n{feedback}\n\nNext Steps:\n{instructions}\n\nBest regards,\nReview Committee"
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
        return True, "Email sent successfully!"
    except Exception as e:
        return False, str(e)

def get_submissions():
    response = supabase.table("submissions").select("*").execute()
    return pd.DataFrame(response.data)

st.set_page_config(page_title="Moellim Course Review", layout="wide")
tab_submit, tab_review = st.tabs(["Submit Course Page", "Reviewer Portal (Admin)"])

with tab_submit:
    st.header("Moellim Course Page Submission")
    with st.form("faculty_submission", clear_on_submit=True):
        course = st.text_input("Course Title & Code *")
        instructor = st.text_input("Instructor Name *")
        email = st.text_input("Instructor Email *")
        pdf = st.file_uploader("Upload Moellim Page PDF *", type=["pdf"])

        submitted = st.form_submit_button("Submit")
        if submitted:
            if not course or not instructor or not email or not pdf:
                st.error("Please fill in all fields and attach the PDF.")
            # --- GUARDRAIL: FILE SIZE CHECK (15MB Limit) ---
            elif pdf.size > 15 * 1024 * 1024:
                st.error("File size exceeds 15MB. Please upload a smaller file.")
            else:
                # --- ENHANCEMENT: TIMESTAMPED UNIQUE FILENAME ---
                timestamp = int(time.time())
                clean_course = "".join(c if c.isalnum() else "_" for c in course)
                clean_instructor = "".join(c if c.isalnum() else "_" for c in instructor)
                clean_name = f"{timestamp}_{clean_course}_{clean_instructor}.pdf"
                
                file_bytes = pdf.read()
                
                # Upload to Supabase Bucket with upsert enabled
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
                st.success(f"Successfully submitted for {course}!")

# --- TAB 2: REVIEWER PORTAL ---
with tab_review:
    st.header("Reviewer Portal")
    admin_pw = st.text_input("Enter Reviewer Password", type="password")
    
    if admin_pw == st.secrets.get("ADMIN_PASSWORD", "admin123"):
        df = get_submissions()
        if df.empty:
            st.info("No submissions yet.")
        else:
            st.dataframe(df, use_container_width=True)
            course_choice = st.selectbox("Select course to evaluate:", df["course_title"].tolist())
            row = df[df["course_title"] == course_choice].iloc[0]

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Instructor:** {row['instructor_name']}")
                st.write(f"**Email:** {row['email']}")
                st.markdown(f"[View/Download Submitted PDF]({row['pdf_url']})")

            with col2:
                status = st.selectbox("Decision", ["Approved", "Needs revision", "Approved with changes"])
                feedback = st.text_area("Remarks", value=str(row['feedback']) if pd.notna(row['feedback']) else "")

                if st.button("Save Evaluation & Send Email"):
                    supabase.table("submissions").update({
                        "status": status,
                        "feedback": feedback
                    }).eq("course_title", course_choice).execute()

                    success, msg = send_review_email(row['email'], row['instructor_name'], course_choice, status, feedback)
                    if success:
                        st.success(f"Saved & emailed to {row['email']}!")
                    else:
                        st.warning(f"Saved to DB, email failed: {msg}")
                    st.rerun()
    elif admin_pw:
        st.error("Incorrect password.")