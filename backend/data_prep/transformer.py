"""
transformer.py
--------------
Data Transformation for GPU Demand Forecasting.

Reads raw job trace events from dataset/raw/job_info_df.csv and converts them
into a continuous hourly time-series of active GPU / CPU demand, broken down by
job_type (HP = High Priority, Spot).

Algorithm:
  - Every job is alive during the interval [submit_time, submit_time + duration).
  - For each 1-hour bucket h (hours since t=0) we count the TOTAL gpu_request and
    cpu_request that was active at any point during that hour, weighted by the
    fraction of the hour the job was actually running (i.e. a job counts fully if
    it spans the entire hour, proportionally if it only overlaps part of it).
  - Results are pivoted by job_type so the output has columns:
      hour_index, gpu_HP, cpu_HP, gpu_Spot, cpu_Spot, gpu_total, cpu_total

Output: dataset/processed/hourly_gpu_demand.csv
"""

import os
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_CSV = os.path.join(BASE_DIR, "dataset", "raw", "job_info_df.csv")
OUT_DIR = os.path.join(BASE_DIR, "dataset", "processed")
OUT_CSV = os.path.join(OUT_DIR, "hourly_gpu_demand.csv")

SECONDS_PER_HOUR = 3600


def load_raw(path: str) -> pd.DataFrame:
    """Load the raw CSV and keep only the columns we need."""
    print(f"[1/4] Loading raw data from: {path}")
    df = pd.read_csv(
        path,
        usecols=["submit_time", "duration", "gpu_request", "cpu_request", "job_type"],
        dtype={
            "submit_time": "float64",
            "duration": "float64",
            "gpu_request": "float64",
            "cpu_request": "float64",
            "job_type": "str",
        },
    )
    print(f"       Loaded {len(df):,} rows. job_type distribution:")
    print(df["job_type"].value_counts().to_string(header=False))
    return df


def build_hourly_demand(df: pd.DataFrame) -> pd.DataFrame:
    """
    For every hour bucket [h*3600, (h+1)*3600) compute the SUM of:
        gpu_request * overlap_fraction
        cpu_request * overlap_fraction
    where overlap_fraction = (overlap_seconds / 3600) for each active job.

    Returns a long-form DataFrame with columns:
        hour_index, job_type, gpu_demand, cpu_demand
    """
    print("[2/4] Computing job start / end times in seconds ...")
    df = df.copy()
    df["t_start"] = df["submit_time"]
    df["t_end"] = df["submit_time"] + df["duration"]

    # Drop zero-duration jobs (shouldn't happen but be safe)
    df = df[df["duration"] > 0].reset_index(drop=True)

    # Determine the full timeline in hours
    global_end_sec = df["t_end"].max()
    n_hours = int(np.ceil(global_end_sec / SECONDS_PER_HOUR))

    print(
        f"       Timeline: 0 - {global_end_sec/SECONDS_PER_HOUR:,.1f} hours  "
        f"->  {n_hours:,} hourly buckets"
    )

    # Pre-compute per-job start / end in fractional hours for fast vectorised ops
    h_start = df["t_start"].values / SECONDS_PER_HOUR
    h_end = df["t_end"].values / SECONDS_PER_HOUR
    gpu = df["gpu_request"].values
    cpu = df["cpu_request"].values
    jtype = df["job_type"].values

    job_types = df["job_type"].unique().tolist()

    print(f"[3/4] Aggregating demand into {n_hours:,} hourly buckets ...")

    # We build result arrays per job_type
    results = {
        jt: {"gpu": np.zeros(n_hours, dtype=np.float64),
             "cpu": np.zeros(n_hours, dtype=np.float64)}
        for jt in job_types
    }

    # Vectorised loop over each job type separately for memory efficiency
    for jt in job_types:
        mask = jtype == jt
        hs = h_start[mask]
        he = h_end[mask]
        g = gpu[mask]
        c = cpu[mask]

        # For each job find the range of hours it touches
        first_hour = np.floor(hs).astype(np.int64)
        last_hour = np.minimum(np.ceil(he).astype(np.int64), n_hours)  # exclusive

        gpu_arr = results[jt]["gpu"]
        cpu_arr = results[jt]["cpu"]

        # Iterate over jobs; use numpy broadcasting per job (inner loop is hours)
        for i in range(len(hs)):
            fh = first_hour[i]
            lh = last_hour[i]
            if fh >= n_hours:
                continue

            # Hour indices this job touches
            hours = np.arange(fh, lh)

            # Overlap of job [hs, he] with bucket [h, h+1]
            overlap_start = np.maximum(hs[i], hours.astype(np.float64))
            overlap_end = np.minimum(he[i], hours.astype(np.float64) + 1.0)
            fraction = np.clip(overlap_end - overlap_start, 0.0, 1.0)

            gpu_arr[hours] += g[i] * fraction
            cpu_arr[hours] += c[i] * fraction

    # Assemble long-form result
    frames = []
    for jt in job_types:
        tmp = pd.DataFrame(
            {
                "hour_index": np.arange(n_hours),
                "job_type": jt,
                "gpu_demand": results[jt]["gpu"],
                "cpu_demand": results[jt]["cpu"],
            }
        )
        frames.append(tmp)

    long_df = pd.concat(frames, ignore_index=True)
    return long_df


def pivot_and_save(long_df: pd.DataFrame, out_path: str) -> pd.DataFrame:
    """Pivot to wide format, add totals column, and save to CSV."""
    print("[4/4] Pivoting to wide format and saving ...")

    # Pivot
    gpu_wide = long_df.pivot(index="hour_index", columns="job_type", values="gpu_demand")
    cpu_wide = long_df.pivot(index="hour_index", columns="job_type", values="cpu_demand")

    gpu_wide.columns = [f"gpu_{c}" for c in gpu_wide.columns]
    cpu_wide.columns = [f"cpu_{c}" for c in cpu_wide.columns]

    result = pd.concat([gpu_wide, cpu_wide], axis=1).reset_index()
    result.fillna(0.0, inplace=True)

    # Totals
    gpu_cols = [c for c in result.columns if c.startswith("gpu_")]
    cpu_cols = [c for c in result.columns if c.startswith("cpu_")]
    result["gpu_total"] = result[gpu_cols].sum(axis=1)
    result["cpu_total"] = result[cpu_cols].sum(axis=1)

    # Round to 4 decimal places for readability
    numeric_cols = [c for c in result.columns if c != "hour_index"]
    result[numeric_cols] = result[numeric_cols].round(4)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result.to_csv(out_path, index=False)
    print(f"\n[OK] Saved {len(result):,} rows -> {out_path}")
    return result


def main():
    df_raw = load_raw(RAW_CSV)
    long_df = build_hourly_demand(df_raw)
    result = pivot_and_save(long_df, OUT_CSV)

    print("\n--- First 5 rows of hourly_gpu_demand.csv ---")
    print(result.head().to_string(index=False))
    print("\nColumns:", list(result.columns))
    print("Shape  :", result.shape)


if __name__ == "__main__":
    main()
