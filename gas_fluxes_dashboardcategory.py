import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import tempfile
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
        df[col]=pd.to_numeric(df[col], errors="ignore")
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
    doc = SimpleDocTemplate(tmp.name, pagesize=A4)
    styles = getSampleStyleSheet()

    elements = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 20)
    ]

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

    st.title("Element vs. element with site types")

    uploaded_file = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        key="upload_site_type"
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

        # -------- Site type assignment --------
        st.sidebar.subheader("Site Type Assignment")

        site_types = [
            "Suburban industrial", "Urban industrial", "Urban background", "Rural background", "Urban traffic"]
        
        if "site_type_map" not in st.session_state:
            st.session_state.site_type_map={}

        site_type_map = {}

        for site in selected_sites:
            default_value=st.session_state.site_type_map.get(site, site_types[0])
            selected_type = st.sidebar.selectbox(
                f"{site}",
                site_types,
                key=f"type_{site}"
            )
            st.session_state.site_type_map[site] = selected_type
            site_type_map[site] = selected_type
            
        if st.sidebar.button("Reset site types", key="reset_site_types"):
            st.session_state.site_type_map={}

        # -------- Element selection --------
        st.sidebar.subheader("Select Element")

        x_element = st.sidebar.selectbox("X element", numeric_cols)
        y_element = st.sidebar.selectbox("Y element", numeric_cols)

        if x_element == y_element:
            st.warning("Select 2 different elements")
            return
        
        show_labels = st.sidebar.checkbox("Show data points labels(outliers)")
        
        # -------- Calculate site means --------
        corr_df = df.copy()
        corr_df = corr_df.groupby(["Site"], as_index=False)[[x_element, y_element]].mean()
        corr_df["site_type"] = corr_df["Site"].map(site_type_map).fillna("Unassigned")

        corr_df.replace([np.inf, -np.inf], np.nan, inplace=True)
        
        corr_df["label"] = (
            "Site: " + corr_df["Site"].astype(str) +
            "<br>Type: " + corr_df["site_type"].astype(str) +
            f"<br>{x_element}: " + corr_df[x_element].round(3).astype(str) +
            f"<br>{y_element}: " + corr_df[y_element].round(3).astype(str))
        
        all_sites_for_labels = sorted(corr_df["Site"].unique())
        label_sites = st.sidebar.multiselect("Select Sites to label", options =all_sites_for_labels)
        
        # -------- Plot --------
        color_map = {
            "Suburban industrial": "red",
            "Urban industrial": "green",
            "Urban background": "blue",
            "Rural background": "yellow",
            "Urban traffic": "purple"
        }

        fig = go.Figure()

        for site_type, sub_df in corr_df.groupby("site_type"):
            fig.add_trace(go.Scatter(
                x=sub_df[x_element],
                y=sub_df[y_element],
                mode="markers+text" if show_labels else "markers",
                name=site_type,
                marker=dict(
                    size=15,
                    color=color_map.get(site_type, "black"),
                    line=dict(width=1, color="black")
                ),
                text=sub_df.apply(
                    lambda row: row["label"] if row["Site"] in label_sites else "",
                    axis=1),

                textposition="top center",
                hovertemplate=
                    "Site: %{text}<extra></extra>"
            ))
            fig.update_traces(textfont=dict(size=15))

        corr_value = corr_df[x_element].corr(corr_df[y_element])
        title = f"{y_element} vs {x_element} (r = {corr_value:.2f})"

        fig.update_layout(
            title=title,
            xaxis_title=f"{x_element} (ng/m\u00B3)",
            yaxis_title=f"{y_element} (ng/m\u00B3)",
            template="plotly_white", font=dict(size=25)
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
                create_csv(corr_df),
                "elements_by_site.csv"
            )

    else:
        st.info("Upload a CSV file")
