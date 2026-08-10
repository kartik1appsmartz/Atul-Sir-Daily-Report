# ============================================================
# ANDROID DAILY ACTIVE USERS REPORT
#
# Flow:
# 1. Calculate report date = today - 3 days
# 2. Calculate comparison date = report date - 7 days
# 3. Query BigQuery
# 4. Get total Android active users (separate query)
# 5. Get total Android engaged users + Top 15 countries
# 6. Create a styled report image
# 7. Save image locally with report date
# 8. Build dynamic email subject/body
# 9. Embed report image inside email
# 10. Send email
# ============================================================


# ============================================================
# IMPORTS
# ============================================================

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.cloud import bigquery

import pandas as pd
import matplotlib.pyplot as plt

import os
import ssl
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage


# ============================================================
# CONFIGURATION
# ============================================================

# BigQuery service account JSON file
SERVICE_ACCOUNT_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "service.json"
)

# Email configuration
SENDER_EMAIL = "kartik.goyal@appsmartz.com"
RECEIVER_EMAIL = "rajveer.kaur@appsmartz.com"
# CC_EMAILS=["harshdeep.singla@appsmartz.com"]
BCC_EMAILS = [
    "rajveer.kaur@appsmartz.com"
    
]

# Read Gmail App Password from environment variable
EMAIL_APP_PASSWORD = os.environ.get(
    "EMAIL_APP_PASSWORD",
    "jcfnychorpmsllyk"
)

if not EMAIL_APP_PASSWORD:
    raise ValueError(
        "EMAIL_APP_PASSWORD environment variable is not set."
    )


# ============================================================
# DATE CONFIGURATION
# ============================================================

# Use Indian timezone so the date does not depend on
# the timezone of the server/notebook machine
TIMEZONE = ZoneInfo("Asia/Kolkata")

today = datetime.now(TIMEZONE).date()


# ------------------------------------------------------------
# Report date
#
# Example:
# Today = 07 Aug
# Report date = 04 Aug
# ------------------------------------------------------------

report_date = today - timedelta(days=3)


# ------------------------------------------------------------
# Previous week = exactly 7 days before report date
# ------------------------------------------------------------

previous_date = report_date - timedelta(days=7)


# ------------------------------------------------------------
# BigQuery date format
# YYYYMMDD
# ------------------------------------------------------------

report_date_bq = report_date.strftime("%Y%m%d")
previous_date_bq = previous_date.strftime("%Y%m%d")


# ------------------------------------------------------------
# Display formats
# ------------------------------------------------------------

# Example:
# Tuesday, 04 August 2026
report_date_full = report_date.strftime(
    "%A, %d %B %Y"
)

previous_date_full = previous_date.strftime(
    "%A, %d %B %Y"
)


# Example:
# 04 Aug 2026
report_date_short = report_date.strftime(
    "%d %b %Y"
)

previous_date_short = previous_date.strftime(
    "%d %b %Y"
)


print("========================================")
print("DATE INFORMATION")
print("========================================")

print("Today:", today)
print("Report Date:", report_date_full)
print("Previous Week:", previous_date_full)


# ============================================================
# BIGQUERY CONNECTION
# ============================================================

client = bigquery.Client.from_service_account_json(
    SERVICE_ACCOUNT_PATH
)


# ============================================================
# BIGQUERY QUERIES
# ============================================================

# ------------------------------------------------------------
# QUERY 1: ENGAGED USERS
# Existing logic retained:
#   is_active_user = TRUE
#   event_name = 'session_start'
# Used for the Top 15 country table and engaged-user KPIs.
# ------------------------------------------------------------

engaged_query = f"""

DECLARE target_date STRING DEFAULT '{report_date_bq}';

DECLARE previous_date STRING DEFAULT '{previous_date_bq}';


-- ==========================================================
-- CURRENT REPORT DATE - ENGAGED USERS
-- ==========================================================

WITH current_day AS (

    SELECT

        geo.country AS country,

        COUNT(
            DISTINCT user_pseudo_id
        ) AS users_current

    FROM
        `admob-app-id-6623078720.analytics_153250222.events_*`

    WHERE

        _TABLE_SUFFIX = target_date

        AND platform = 'ANDROID'

        AND is_active_user = TRUE

        AND event_name = 'session_start'

    GROUP BY
        country
),


-- ==========================================================
-- SAME DAY PREVIOUS WEEK - ENGAGED USERS
-- ==========================================================

previous_day AS (

    SELECT

        geo.country AS country,

        COUNT(
            DISTINCT user_pseudo_id
        ) AS users_previous

    FROM
        `admob-app-id-6623078720.analytics_153250222.events_*`

    WHERE

        _TABLE_SUFFIX = previous_date

        AND platform = 'ANDROID'

        AND is_active_user = TRUE

        AND event_name = 'session_start'

    GROUP BY
        country
),


-- ==========================================================
-- TOTAL ENGAGED USERS
-- ==========================================================

totals AS (

    SELECT

        -- Current date total Android engaged users
        (
            SELECT

                COUNT(
                    DISTINCT user_pseudo_id
                )

            FROM
                `admob-app-id-6623078720.analytics_153250222.events_*`

            WHERE

                _TABLE_SUFFIX = target_date

                AND platform = 'ANDROID'

                AND is_active_user = TRUE

                AND event_name = 'session_start'

        ) AS total_engaged_users_current,


        -- Previous week total Android engaged users
        (
            SELECT

                COUNT(
                    DISTINCT user_pseudo_id
                )

            FROM
                `admob-app-id-6623078720.analytics_153250222.events_*`

            WHERE

                _TABLE_SUFFIX = previous_date

                AND platform = 'ANDROID'

                AND is_active_user = TRUE

                AND event_name = 'session_start'

        ) AS total_engaged_users_previous
)


-- ==========================================================
-- FINAL OUTPUT
-- ==========================================================

SELECT

    c.country,

    c.users_current,

    COALESCE(
        p.users_previous,
        0
    ) AS users_previous,


    ROUND(

        SAFE_DIVIDE(

            c.users_current -
            COALESCE(
                p.users_previous,
                0
            ),

            NULLIF(
                COALESCE(
                    p.users_previous,
                    0
                ),
                0
            )

        ) * 100,

        2

    ) AS pct_change_vs_7_days_ago,


    t.total_engaged_users_current,

    t.total_engaged_users_previous


FROM
    current_day c


LEFT JOIN
    previous_day p

USING(country)


CROSS JOIN
    totals t


WHERE
    c.country IS NOT NULL


ORDER BY
    c.users_current DESC


LIMIT 15

"""


# ------------------------------------------------------------
# QUERY 2: TOTAL ACTIVE USERS
# New query requested by you. This intentionally does NOT use
# is_active_user = TRUE.
# ------------------------------------------------------------

active_users_query = f"""

DECLARE target_date STRING DEFAULT '{report_date_bq}';
DECLARE previous_date STRING DEFAULT '{previous_date_bq}';

WITH user_counts AS (

    SELECT

        _TABLE_SUFFIX AS date,

        COUNT(DISTINCT user_pseudo_id) AS total_users

    FROM
        `admob-app-id-6623078720.analytics_153250222.events_*`

    WHERE

        _TABLE_SUFFIX IN (target_date, previous_date)

        AND platform = 'ANDROID'

        AND event_name = 'session_start'

    GROUP BY
        date
)

SELECT

    date,

    total_users

FROM user_counts

ORDER BY date;

"""


# ============================================================
# RUN BIGQUERY QUERIES
# ============================================================

print("\nRunning engaged-users BigQuery query...")

engaged_query_job = client.query(engaged_query)

df = engaged_query_job.to_dataframe()


print("\nRunning total-active-users BigQuery query...")

active_query_job = client.query(active_users_query)

active_df = active_query_job.to_dataframe()


# ============================================================
# VALIDATE DATA
# ============================================================

if df.empty:

    raise ValueError(
        f"No Android engaged-user data found for "
        f"{report_date_full}"
    )


if active_df.empty:

    raise ValueError(
        f"No Android total-active-user data found for "
        f"{report_date_full}"
    )


print("\nQueries completed successfully.")

print("\nTop engaged-user rows:")
print(df.head())

print("\nTotal active-user rows:")
print(active_df)


# ============================================================
# TOTAL ANDROID ENGAGED USERS
# ============================================================

engaged_current = int(
    df["total_engaged_users_current"].iloc[0]
)

engaged_previous = int(
    df["total_engaged_users_previous"].iloc[0]
)


if engaged_previous > 0:

    engaged_change_pct = (
        (engaged_current - engaged_previous)
        / engaged_previous
    ) * 100

else:

    engaged_change_pct = None


if engaged_change_pct is None:

    engaged_change_text = "N/A"

elif engaged_change_pct >= 0:

    engaged_change_text = (
        f"▲ {engaged_change_pct:.2f}%"
    )

else:

    engaged_change_text = (
        f"▼ {abs(engaged_change_pct):.2f}%"
    )


engaged_difference = (
    engaged_current - engaged_previous
)


# ============================================================
# TOTAL ANDROID ACTIVE USERS
# ============================================================

active_counts = {
    str(row["date"]): int(row["total_users"])
    for _, row in active_df.iterrows()
}

if report_date_bq not in active_counts:

    raise ValueError(
        f"No Android total-active-user data found for "
        f"{report_date_full}"
    )

if previous_date_bq not in active_counts:

    raise ValueError(
        f"No Android total-active-user data found for "
        f"{previous_date_full}"
    )


active_current = active_counts[report_date_bq]
active_previous = active_counts[previous_date_bq]


if active_previous > 0:

    active_change_pct = (
        (active_current - active_previous)
        / active_previous
    ) * 100

else:

    active_change_pct = None


if active_change_pct is None:

    active_change_text = "N/A"

elif active_change_pct >= 0:

    active_change_text = (
        f"▲ {active_change_pct:.2f}%"
    )

else:

    active_change_text = (
        f"▼ {abs(active_change_pct):.2f}%"
    )


active_difference = (
    active_current - active_previous
)


print("\n========================================")
print("ANDROID USER SUMMARY")
print("========================================")

print(
    f"Total Active Users - {report_date_full}: "
    f"{active_current:,}"
)

print(
    f"Total Active Users - {previous_date_full}: "
    f"{active_previous:,}"
)

print(
    f"Active Users 7-Day Change: "
    f"{active_change_text}"
)

print(
    f"Total Engaged Users - {report_date_full}: "
    f"{engaged_current:,}"
)

print(
    f"Total Engaged Users - {previous_date_full}: "
    f"{engaged_previous:,}"
)

print(
    f"Engaged Users 7-Day Change: "
    f"{engaged_change_text}"
)


# ============================================================
# PREPARE TOP 15 COUNTRY DATA
# ============================================================

table_df = df[
    [
        "country",
        "users_current",
        "users_previous",
        "pct_change_vs_7_days_ago"
    ]
].copy()


# ------------------------------------------------------------
# Rename columns dynamically
# ------------------------------------------------------------

table_df.rename(

    columns={

        "country":
            "Country",

        "users_current":
            report_date_short,

        "users_previous":
            previous_date_short,

        "pct_change_vs_7_days_ago":
            "7-Day Change"

    },

    inplace=True
)


# ------------------------------------------------------------
# Sort highest current users first
# ------------------------------------------------------------

table_df = table_df.sort_values(

    report_date_short,

    ascending=False

).reset_index(drop=True)


# ============================================================
# CREATE FORMATTED DISPLAY DATAFRAME
# ============================================================

display_df = table_df.copy()


# Current values
display_df[report_date_short] = (

    display_df[report_date_short]

    .map(
        lambda x: f"{x:,.0f}"
    )
)


# Previous values
display_df[previous_date_short] = (

    display_df[previous_date_short]

    .map(
        lambda x: f"{x:,.0f}"
    )
)


# ------------------------------------------------------------
# Function to format percentage
# ------------------------------------------------------------

def format_change(value):

    if pd.isna(value):

        return "N/A"

    elif value >= 0:

        return f"▲ {value:.2f}%"

    else:

        return f"▼ {abs(value):.2f}%"


display_df["7-Day Change"] = (

    display_df["7-Day Change"]

    .map(format_change)
)


# ============================================================
# CREATE REPORT IMAGE
# ============================================================

fig, ax = plt.subplots(
    figsize=(12, 11)
)

ax.axis("off")


# ============================================================
# REPORT TITLE
# ============================================================

fig.text(

    0.07,
    0.955,

    "Android Daily Active & Engaged Users Report",

    fontsize=24,

    fontweight="bold"
)


# ============================================================
# DATE SUBTITLE
# ============================================================

fig.text(

    0.07,
    0.918,

    (
        f"{report_date_full}  vs  "
        f"{previous_date_full}"
    ),

    fontsize=11,

    color="#6B7280"
)


# ============================================================
# ROW 1: TOTAL ACTIVE USERS
# ============================================================

fig.text(
    0.07,
    0.855,
    f"{active_current:,}",
    fontsize=24,
    fontweight="bold",
    color="#111827"
)

fig.text(
    0.07,
    0.827,
    "Total Active Users (Android only)",
    fontsize=10,
    color="#6B7280"
)

fig.text(
    0.07,
    0.807,
    report_date_full,
    fontsize=8.5,
    color="#9CA3AF"
)

fig.text(
    0.39,
    0.855,
    f"{active_previous:,}",
    fontsize=24,
    fontweight="bold",
    color="#111827"
)

fig.text(
    0.39,
    0.827,
    "Total Active Users – Previous Week",
    fontsize=10,
    color="#6B7280"
)

fig.text(
    0.39,
    0.807,
    previous_date_full,
    fontsize=8.5,
    color="#9CA3AF"
)

if active_change_pct is not None and active_change_pct >= 0:
    active_change_color = "#15803D"
else:
    active_change_color = "#B91C1C"

fig.text(
    0.73,
    0.855,
    active_change_text,
    fontsize=21,
    fontweight="bold",
    color=active_change_color
)

fig.text(
    0.73,
    0.827,
    "Active Users Change vs Previous Week",
    fontsize=10,
    color="#6B7280"
)


# ============================================================
# ROW 2: TOTAL ENGAGED USERS
# ============================================================

fig.text(
    0.07,
    0.745,
    f"{engaged_current:,}",
    fontsize=24,
    fontweight="bold",
    color="#111827"
)

fig.text(
    0.07,
    0.717,
    "Total Engaged Users (Android only)",
    fontsize=10,
    color="#6B7280"
)

fig.text(
    0.07,
    0.697,
    report_date_full,
    fontsize=8.5,
    color="#9CA3AF"
)

fig.text(
    0.39,
    0.745,
    f"{engaged_previous:,}",
    fontsize=24,
    fontweight="bold",
    color="#111827"
)

fig.text(
    0.39,
    0.717,
    "Total Engaged Users – Previous Week",
    fontsize=10,
    color="#6B7280"
)

fig.text(
    0.39,
    0.697,
    previous_date_full,
    fontsize=8.5,
    color="#9CA3AF"
)

if engaged_change_pct is not None and engaged_change_pct >= 0:
    engaged_change_color = "#15803D"
else:
    engaged_change_color = "#B91C1C"

fig.text(
    0.73,
    0.745,
    engaged_change_text,
    fontsize=21,
    fontweight="bold",
    color=engaged_change_color
)

fig.text(
    0.73,
    0.717,
    "Engaged Users Change vs Previous Week",
    fontsize=10,
    color="#6B7280"
)


# ============================================================
# TABLE HEADING
# ============================================================

fig.text(

    0.07,
    0.625,

    "Top 15 Countries",

    fontsize=14,

    fontweight="bold",

    color="#111827"
)

fig.text(

    0.07,
    0.602,

    "Android engaged users by country",

    fontsize=9.5,

    color="#6B7280"
)


# ============================================================
# CREATE TABLE
# ============================================================

table = ax.table(

    cellText=display_df.values,

    colLabels=display_df.columns,

    cellLoc="center",

    colLoc="center",

    loc="center",

    bbox=[
        0.05,   # left
        0.02,   # bottom
        0.90,   # width
        0.53    # height
    ],

    colWidths=[
        0.30,
        0.22,
        0.22,
        0.22
    ]
)


table.auto_set_font_size(False)

table.set_fontsize(10.5)


# ============================================================
# STYLE TABLE
# ============================================================

for (row, col), cell in table.get_celld().items():


    # Light borders
    cell.set_edgecolor("#E5E7EB")

    cell.set_linewidth(0.6)


    # ========================================================
    # HEADER
    # ========================================================

    if row == 0:

        cell.set_facecolor(
            "#1F2937"
        )

        cell.set_text_props(

            color="white",

            weight="bold"
        )


    # ========================================================
    # DATA ROWS
    # ========================================================

    else:


        # Alternate row background
        if row % 2 == 0:

            cell.set_facecolor(
                "#F8FAFC"
            )

        else:

            cell.set_facecolor(
                "#FFFFFF"
            )


        # Country names
        if col == 0:

            cell.get_text().set_ha(
                "left"
            )

            cell.get_text().set_fontweight(
                "bold"
            )


        # ====================================================
        # CHANGE COLUMN
        # ====================================================

        if col == 3:

            pct = table_df.iloc[
                row - 1
            ]["7-Day Change"]


            if pd.isna(pct):

                cell.set_facecolor(
                    "#F3F4F6"
                )

                cell.get_text().set_color(
                    "#6B7280"
                )


            elif pct >= 0:

                cell.set_facecolor(
                    "#DCFCE7"
                )

                cell.get_text().set_color(
                    "#15803D"
                )


            else:

                cell.set_facecolor(
                    "#FEE2E2"
                )

                cell.get_text().set_color(
                    "#B91C1C"
                )


            cell.get_text().set_fontweight(
                "bold"
            )


# ============================================================
# SAVE REPORT IMAGE LOCALLY
# ============================================================

REPORT_FOLDER = (
    "Daily_Active_Users_Reports"
)


# Create folder automatically
os.makedirs(
    REPORT_FOLDER,
    exist_ok=True
)


# Example:
# Android_Daily_Active_Engaged_Users_04_August_2026.png

image_date = report_date.strftime(
    "%d_%B_%Y"
)


IMAGE_FILE = os.path.join(

    REPORT_FOLDER,

    (
        f"Android_Daily_Active_Engaged_Users_"
        f"{image_date}.png"
    )
)


# Save high-resolution image
plt.savefig(

    IMAGE_FILE,

    dpi=300,

    bbox_inches="tight",

    facecolor="white"
)


# Close figure instead of opening it
# Better for automated daily reports
plt.close(fig)


print("\n========================================")
print("IMAGE CREATED")
print("========================================")

print(
    "Saved at:",
    os.path.abspath(IMAGE_FILE)
)


# ============================================================
# EMAIL SUBJECT
# ============================================================

email_subject = (

    f"Android Daily Active & Engaged Users Report – "

    f"{report_date_full} "

    f"vs "

    f"{previous_date_full}"
)


# ============================================================
# EMAIL BODY
# ============================================================

html_body = f"""
<html>

<body style="
    margin:0;
    padding:0;
    background-color:#F4F6F8;
    font-family:Arial, Helvetica, sans-serif;
">

<div style="
    max-width:900px;
    margin:20px auto;
    background-color:#FFFFFF;
    padding:30px;
    border-radius:10px;
">

    <p style="
        font-size:15px;
        color:#111827;
        margin-top:0;
    ">
        Hi Sir,
    </p>

    <p style="
        font-size:15px;
        color:#374151;
        line-height:1.6;
    ">
        Please find below the
        <strong>Daily Active & Engaged Users Report for Android</strong>.
    </p>

    <p style="
        margin-top:25px;
        font-size:15px;
        color:#374151;
        line-height:1.6;
    ">
        The report shows total Android active users from the separate
        session-start query, total engaged users from the existing
        is_active_user = TRUE logic, and the Top 15 countries by engaged users
        for <strong>{report_date_full}</strong>, compared with
        <strong>{previous_date_full}</strong>.
    </p>

    <div style="
        margin-top:20px;
        text-align:center;
    ">
        <img
            src="cid:daily_report_image"
            alt="Android Daily Active and Engaged Users Report"
            style="
                width:100%;
                max-width:850px;
                height:auto;
                border:1px solid #E5E7EB;
                border-radius:8px;
            "
        />
    </div>

    <p style="
        margin-top:30px;
        font-size:14px;
        color:#374151;
        line-height:1.5;
    ">
        Regards,
        <br>
        Kartik Goyal
    </p>

</div>

</body>

</html>

"""


# ============================================================
# PLAIN-TEXT EMAIL FALLBACK
# ============================================================

plain_text = f"""
Hi Sir,

Please find below the Daily Active & Engaged Users Report for Android.

TOTAL ACTIVE USERS
{report_date_full}: {active_current:,}
{previous_date_full}: {active_previous:,}
7-Day Change: {active_change_text}
Net Difference: {active_difference:+,} active users

TOTAL ENGAGED USERS
{report_date_full}: {engaged_current:,}
{previous_date_full}: {engaged_previous:,}
7-Day Change: {engaged_change_text}
Net Difference: {engaged_difference:+,} engaged users

The Top 15 country table is based on Android engaged users.

Regards,
Kartik Goyal
"""


# ============================================================
# CREATE EMAIL MESSAGE
# ============================================================

message = MIMEMultipart("related")


message["From"] = SENDER_EMAIL

message["To"] = RECEIVER_EMAIL
# message["Cc"] = ", ".join(CC_EMAILS)
# message["Bcc"] = ", ".join(BCC_EMAILS)
message["Subject"] = email_subject


# ============================================================
# CREATE ALTERNATIVE TEXT + HTML PART
# ============================================================

alternative = MIMEMultipart(
    "alternative"
)


message.attach(
    alternative
)


# Plain text
alternative.attach(

    MIMEText(
        plain_text,
        "plain",
        "utf-8"
    )
)


# HTML
alternative.attach(

    MIMEText(
        html_body,
        "html",
        "utf-8"
    )
)


# ============================================================
# EMBED SAVED IMAGE INSIDE EMAIL
# ============================================================

with open(
    IMAGE_FILE,
    "rb"
) as image_file:

    report_image = MIMEImage(
        image_file.read()
    )


    # Content-ID used by:
    # src="cid:daily_report_image"

    report_image.add_header(

        "Content-ID",

        "<daily_report_image>"
    )


    report_image.add_header(

        "Content-Disposition",

        "inline",

        filename=os.path.basename(
            IMAGE_FILE
        )
    )


    message.attach(
        report_image
    )


# ============================================================
# SEND EMAIL
# ============================================================

print("\nSending email...")


ssl_context = ssl.create_default_context()


with smtplib.SMTP(
    "smtp.gmail.com",
    587
) as server:


    server.ehlo()


    server.starttls(
        context=ssl_context
    )


    server.ehlo()


    server.login(

        SENDER_EMAIL,

        EMAIL_APP_PASSWORD
    )


    server.send_message(
        message
    )


# ============================================================
# SUCCESS
# ============================================================

print("\n========================================")
print("EMAIL SENT SUCCESSFULLY")
print("========================================")

print(
    "To:",
    RECEIVER_EMAIL
)

print(
    "Subject:",
    email_subject
)

print(
    "Report Date:",
    report_date_full
)

print(
    "Total Android Active Users:",
    f"{active_current:,}"
)

print(
    "Previous Week Android Active Users:",
    f"{active_previous:,}"
)

print(
    "Active Users 7-Day Change:",
    active_change_text
)

print(
    "Total Android Engaged Users:",
    f"{engaged_current:,}"
)

print(
    "Previous Week Android Engaged Users:",
    f"{engaged_previous:,}"
)

print(
    "Engaged Users 7-Day Change:",
    engaged_change_text
)

print(
    "Image Saved:",
    os.path.abspath(IMAGE_FILE)
)
print("To:", RECEIVER_EMAIL)
# print("CC:", CC_EMAILS)
# print("BCC:", BCC_EMAILS)