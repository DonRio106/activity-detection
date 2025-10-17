import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- Config ---
TFLO_ON_THRESHOLD = 10.0
MIN_ACTIVITY_SECONDS = 10
REAM_DELTA_FT = 3.0
BACK_DELTA_FT = 20.0
SENTINEL = -999.25
STRIP_COLOR = "#1f77b4"
STRIP_ALPHA = 0.22

st.set_page_config(page_title="BPOS Activity Viewer", layout="wide")
st.title("BPOS Activity Viewer (Ream + Backream — Blue Strips)")

uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if not uploaded:
    st.info("Upload an Excel file to start.")
    st.stop()

# Load and clean data
df = pd.read_excel(uploaded, engine="openpyxl")
df.columns = [c.strip() for c in df.columns]
if "Date" in df.columns:
    ts = pd.to_datetime(df["Date"], errors="coerce")
elif "Time" in df.columns:
    ts = pd.to_datetime(df["Time"], errors="coerce")
else:
    ts = pd.to_datetime(df.iloc[:, 0], errors="coerce")
df["timestamp"] = ts
df = df.replace(SENTINEL, np.nan)
for c in ["TFLO", "DBTM", "CDEPTH", "BPOS"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

# Detect activity segments
pump_on = (df["TFLO"] > TFLO_ON_THRESHOLD).fillna(False)
delta = df["DBTM"] - df["CDEPTH"]
cond_any = (delta >= REAM_DELTA_FT) | ((-delta) >= BACK_DELTA_FT)
mask = pump_on & cond_any & df["DBTM"].notna() & df["CDEPTH"].notna()

segments = []
if mask.any():
    m = mask.astype(int)
    dm = m.diff().fillna(0)
    starts = dm[dm == 1].index.tolist()
    ends = dm[dm == -1].index.tolist()
    if mask.iloc[0]:
        starts = [mask.index[0]] + starts
    if mask.iloc[-1]:
        ends = ends + [mask.index[-1]]
    for s, e in zip(starts, ends):
        t0 = df.loc[s, "timestamp"]
        t1 = df.loc[e, "timestamp"]
        dur_sec = (t1 - t0).total_seconds()
        if dur_sec >= MIN_ACTIVITY_SECONDS:
            excursion_ft = float(np.nanmax(np.abs(delta[s:e+1])))
            segments.append({"t_start": t0, "t_end": t1, "duration_sec": dur_sec, "excursion_ft": excursion_ft})

seg_df = pd.DataFrame(segments)

# Summary
st.metric("Segments", len(seg_df))
st.metric("Total Duration (min)", f"{seg_df['duration_sec'].sum()/60:.1f}" if len(seg_df) else "0.0")

# Plot
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["timestamp"], y=df["BPOS"], mode="lines", name="BPOS", line=dict(color="black")))
for _, s in seg_df.iterrows():
    fig.add_shape(type="rect", xref="x", yref="paper",
                  x0=s["t_start"], x1=s["t_end"], y0=0, y1=1,
                  fillcolor=STRIP_COLOR, opacity=STRIP_ALPHA, line=dict(width=0))
fig.update_layout(title="BPOS with Activity Strips", xaxis=dict(rangeslider=dict(visible=True)), yaxis_title="BPOS (ft)")
st.plotly_chart(fig, use_container_width=True)

# Download CSV
st.download_button("Download Segments CSV", seg_df.to_csv(index=False).encode("utf-8"), "activity_segments.csv", "text/csv")