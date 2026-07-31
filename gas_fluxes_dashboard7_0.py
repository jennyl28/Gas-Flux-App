import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import tempfile
import io
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet


# ---------------- CLEANING ----------------

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
    st.write(df.head() if hasattr(df, "head") else df)
    return df.map(clean_detection_limits).apply(pd.to_numeric, errors="coerce")


# ---------------- EXTRACTION ----------------

def extract_tables(file):
    content = file.read().decode("utf-8", errors="coerce")
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
    df["Site"] = site

    return df


# ---------------- EXPORT ----------------

def create_pdf(fig, title):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    img_bytes = fig.to_image(format="png")
    img_buffer = io.BytesIO(img_bytes)
    doc = SimpleDocTemplate(tmp.name)
    styles = getSampleStyleSheet()

    elements = [Paragraph(title, styles["Title"]), Spacer(1, 20)]
    doc.build(elements)
    with open(tmp.name, "rb") as f:
        pdf = f.read()
    return pdf

    try:
        img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        fig.write_image(img.name)
        elements.append(Image(img.name, width=500, height=300))
    except:
        elements.append(Paragraph("Image export failed", styles["Normal"]))

    doc.build(elements)
    return tmp.name


def create_csv(df):
    return df.to_csv(index=False).encode("utf-8")


# ---------------- MAIN APP ----------------

def run():

    st.title("Element ratio vs. element ratio with site types")

    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="upload_ratio_combined")

    if not uploaded_file:
        st.info("Upload a CSV file")
        return

    # -------- Load data --------
    tables = extract_tables(uploaded_file)

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
    selected_sites = st.sidebar.multiselect("Site", sites, default=list(sites[:5]))

    df = df_all[df_all["Site"].isin(selected_sites)]

    numeric_cols = df.select_dtypes(include=np.number).columns.tolist()

    # -------- Ratio selection --------
    st.sidebar.subheader("Select Ratios")

    ratio_pairs = []

    for i in range(2):
        col1, col2 = st.sidebar.columns(2)

        with col1:
            num = st.selectbox(f"Numerator {i+1}", ["None"] + numeric_cols, key=f"num_{i}")

        with col2:
            den = st.selectbox(f"Denominator {i+1}", ["None"] + numeric_cols, key=f"den_{i}")

        if num != "None" and den != "None" and num != den:
            ratio_pairs.append((num, den))

    if len(ratio_pairs) < 2:
        st.warning("Select two ratios")
        return

    # -------- Calculate ratios --------
    ratio_df = df.copy()

    for num, den in ratio_pairs:
        ratio_df[f"{num}/{den}"] = ratio_df[num] / ratio_df[den]

    ratio_df.replace([np.inf, -np.inf], np.nan, inplace=True)

    ratio_cols = [f"{n}/{d}" for n, d in ratio_pairs]

    ratio_df = ratio_df.groupby("Site", as_index=False)[ratio_cols].mean()

    # -------- Site type assignment --------
    st.sidebar.subheader("Site Type")

    site_types = ["Suburban industrial", "Urban industrial", "Urban background", "Rural background", "Urban traffic"]

    if "site_type_map" not in st.session_state:
        st.session_state.site_type_map = {}

    site_type_map = {}

    for site in selected_sites:
        default = st.session_state.site_type_map.get(site, site_types[0])

        selected = st.sidebar.selectbox(
            site,
            site_types,
            index=site_types.index(default),
            key=f"type_{site}"
        )

        st.session_state.site_type_map[site] = selected
        site_type_map[site] = selected

    if st.sidebar.button("Reset site types", key="reset_types_combined"):
        st.session_state.site_type_map = {}

    ratio_df["site_type"] = ratio_df["Site"].map(site_type_map).fillna("Unassigned")
    
    show_labels = st.sidebar.checkbox("Show data points labels(outliers)")

    # -------- Labels --------
    show_labels = st.sidebar.checkbox("Show labels")

    x_ratio = ratio_cols[0]
    y_ratio = ratio_cols[1]

    ratio_df["label"] = (
        "Site: " + ratio_df["Site"] +
        "<br>Type: " + ratio_df["site_type"] +
        f"<br>{x_ratio}: " + ratio_df[x_ratio].round(3).astype(str) +
        f"<br>{y_ratio}: " + ratio_df[y_ratio].round(3).astype(str)
    )
    all_sites_for_labels = sorted(ratio_df["Site"].unique())
    label_sites = st.sidebar.multiselect("Select Sites to label", options =all_sites_for_labels)

    # -------- Plot --------
    color_map = {"Suburban industrial": "red", "Urban industrial": "green", "Urban background": "blue", "Rural background": "yellow", "Urban traffic": "purple"}

    fig = go.Figure()

    for site_type, sub_df in ratio_df.groupby("site_type"):
        fig.add_trace(go.Scatter(
            x=sub_df[x_ratio],
            y=sub_df[y_ratio],
            mode="markers+text" if show_labels else "markers",
            name=site_type,
            marker=dict(size=12, color=color_map.get(site_type, "grey")),
            text=sub_df.apply(
                lambda row: row["label"] if row["Site"] in label_sites else "",
                axis=1),
            textposition="top center",
            hovertemplate="Site: %{text}<extra></extra>"
        ))
        fig.update_traces(textfont=dict(size=12))

    corr = ratio_df[x_ratio].corr(ratio_df[y_ratio])

    title = f"{y_ratio} vs {x_ratio} (r = {corr:.2f})"

    fig.update_layout(
        title=title,
        xaxis_title=f"{x_ratio} (ratio)",
        yaxis_title=f"{y_ratio} (ratio)",
        template="plotly_white"
    )

    st.plotly_chart(fig, use_container_width=True)

    # -------- Export --------
    if st.button("Export PDF", key="pdf_ratio"):
        pdf_path = create_pdf(fig, title)
        with open(pdf_path, "rb") as f:
            st.download_button("Download PDF", f)

    if st.button("Export CSV", key="csv_ratio"):
        st.download_button("Download CSV", create_csv(ratio_df), "ratio_data.csv")
