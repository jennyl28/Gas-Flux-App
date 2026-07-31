import streamlit as st 

try:
  import gas_fluxes_dashboard4_0
  import gas_fluxes_dashboard4_1
  import gas_fluxes_dashboard5_0
  import gas_fluxes_dashboardcategory
  import gas_fluxes_dashboard7_0
except ImportError as e:
  st.error(f"Module import error: {e}")
  st.stop()

def main():
  st.set_page_config(layout="wide")
if __name__ == "__Gas Fluxes Analysis Dashboard__":
  main()
st.title("Gas Fluxes Analysis Dashboard")

st.sidebar.title("Select Dashboard")

dashboard_choice = st.sidebar.selectbox("Select dashboard", ["Element ratios vs. time", "Element ratios averaged vs. time", "Element ratio vs. element ratio", "Element vs. element with site types", "Element ratio vs. element ratio with site types"])

if dashboard_choice == "Element ratios vs. time": gas_fluxes_dashboard4_0.run()

elif dashboard_choice == "Element ratios averaged vs. time": gas_fluxes_dashboard4_1.run()

elif dashboard_choice == "Element ratio vs. element ratio": gas_fluxes_dashboard5_0.run()

elif dashboard_choice == "Element vs. element with site types": gas_fluxes_dashboardcategory.run()

elif dashboard_choice == "Element ratio vs. element ratio with site types": gas_fluxes_dashboard7_0.run()
