import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import tempfile
import io
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

# --------------------------------------------------
# CLEANING FUNCTIONS
# --------------------------------------------------

def clean_columns(df):
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    return df


def clean_detection_limits(value):
    if isinstance(value, str) and "<" in value:
        try:
            return float(value.replace("<", "")) / 2
        except:
            return np.nan
    return value


def convert_numeric(df):
    return df.map(clean_detection_limits)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")
    return df

def extract_tables(file):
    content = file.read().decode("utf-8", errors="ignore")
    lines = content.splitlines()

    tables = []
    current_block = []
    current_site = "Unknown Site"
    capturing = False
    site = "Unknown Site"

    for line in lines:
        if line.strip() == "":
            continue

        parts = [p.strip() for p in line.split(",")]
        line_lower = line.lower()

        if "multi-day data" in line_lower:
            vals = [p for p in parts if p != ""]
            if len(vals) > 1:
                current_site = vals[-1]
            continue

        if "start date" in line_lower and "end date" in line_lower:
            if current_block:
                tables.append((site, pd.DataFrame(current_block)))

            current_block = []
            capturing = True
            site = current_site
            current_block.append(parts)
            continue

        if capturing:
            current_block.append(parts)

    if current_block:
        tables.append((site, pd.DataFrame(current_block)))

    return tables


def process_table(df, site):
    if len(df) < 2:
        return None

    df.columns = df.iloc[0]
    df = df[1:]

    df = clean_columns(df)
    df = convert_numeric(df)

    rename = {}
    for col in df.columns:
        if "start" in col.lower():
            rename[col] = "StartDate"
        if "end" in col.lower():
            rename[col] = "EndDate"

    df = df.rename(columns=rename)

    if "StartDate" not in df.columns:
        return None

    df["StartDate"] = pd.to_datetime(df["StartDate"], errors="coerce")
    df["Year"] = df["StartDate"].dt.year
    df = df.dropna(subset=["StartDate"])
    df["Site"] = site

    return df


def create_pdf(fig, title):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    img_bytes = fig.to_image(format="png")
    img_buffer = io.BytesIO(img_bytes)
    doc = SimpleDocTemplate(tmp.name, pagesize=A4)
    styles = getSampleStyleSheet()

    elements = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 20)
    ]
    with open(tmp.name, "rb" as f:
        pdf= f.read()
    return pdf

    try:
        img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        fig.write_image(img.name, width=900, height=500)
        elements.append(Image(img.name, width=500, height=300))

    except:
        elements.append(Paragraph("Image export failed", styles["Normal"]))

    doc.build(elements)
    return tmp.name


def create_csv(df):
    return df.to_csv(index=False).encode("utf-8")


# --------------------------------------------------
# ✅ MAIN DASHBOARD FUNCTION
# --------------------------------------------------

def run():

    st.title("Element ratio vs. element ratio")

    uploaded_file = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        key="upload_ratio"
    )

    if uploaded_file:

        tables = extract_tables(uploaded_file)
        st.write(f"✅ Tables detected: {len(tables)}")

        all_data = []

        for site, table in tables:
            df = process_table(table, site)
            if df is not None and len(df) > 0:
                all_data.append(df)

        if len(all_data) == 0:
            st.error("No valid data detected")
            return

        df_all = pd.concat(all_data, ignore_index=True)

        # -------- Filters --------
        st.sidebar.header("Filters")

        sites = df_all["Site"].unique()
        selected_sites = st.sidebar.multiselect("Site", sites, default=sites[:5])

        df = df_all[df_all["Site"].isin(selected_sites)]

        date_range = st.sidebar.date_input(
            "Date Range",
            [df["StartDate"].min(), df["StartDate"].max()]
        )

        if len(date_range) == 2:
            df = df[
                (df["StartDate"] >= pd.to_datetime(date_range[0])) &
                (df["StartDate"] <= pd.to_datetime(date_range[1]))
            ]

        numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
        numeric_cols = [c for c in numeric_cols if c not in ["Year"]]

        # -------- Ratio selection --------
        st.sidebar.subheader("Select Element Ratios")

        ratio_pairs = []

        for i in range(2):
            col1, col2 = st.sidebar.columns(2)

            with col1:
                num = st.selectbox(f"Numerator {i+1}", ["None"] + numeric_cols, key=f"n{i}")

            with col2:
                den = st.selectbox(f"Denominator {i+1}", ["None"] + numeric_cols, key=f"d{i}")

            if num != "None" and den != "None" and num != den:
                ratio_pairs.append((num, den))

        if len(ratio_pairs) == 0:
            st.info("Select at least one ratio")
            return

        # -------- Calculate ratios --------
        ratio_df = df.copy()

        for num, den in ratio_pairs:
            ratio_df[f"{num}/{den}"] = ratio_df[num] / ratio_df[den]

        ratio_df.replace([np.inf, -np.inf], np.nan, inplace=True)

        ratio_cols = [f"{n}/{d}" for n, d in ratio_pairs]

        ratio_df = ratio_df.groupby(["Site"], as_index=False)[ratio_cols].mean()
        ratio_df = ratio_df.sort_values(by=["Site"])

        # -------- Plot --------
        if len(ratio_cols) < 2:
            st.warning("Select two ratios for comparison")
            return

        x_ratio = ratio_cols[0]
        y_ratio = ratio_cols[1]

        fig = go.Figure()

        for site in ratio_df["Site"].unique():
            site_df = ratio_df[ratio_df["Site"] == site]

            fig.add_trace(go.Scatter(
                x=site_df[x_ratio],
                y=site_df[y_ratio],
                mode="markers",
                marker=dict(size=12),
                name=site
            ))

        title = f"{y_ratio} vs {x_ratio} (by Site)"   # ✅ FIXED

        fig.update_layout(
            title=title,
            xaxis_title=x_ratio,
            yaxis_title=y_ratio,
            template="plotly_white"
        )

        st.plotly_chart(fig, use_container_width=True)

        # -------- Export --------
        if st.button("Export PDF"):
            pdf_path = create_pdf(fig, title)
            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF", f)

        if st.button("Export CSV"):
            st.download_button(
                "Download CSV",
                create_csv(ratio_df),
                "element_ratios_by_site.csv"
            )

    else:
        st.info("Upload a CSV file")
