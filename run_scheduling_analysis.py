import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)

def load_swf(filename, max_rows=200):
    data = []
    if not os.path.exists(filename):
        print(f"Warning: {filename} not found.")
        return pd.DataFrame()
        
    with open(filename, 'r') as f:
        count = 0
        for line in f:
            line = line.strip()
            if not line or line.startswith(';'): continue
            parts = line.split()
            if len(parts) < 18: continue
            try:
                pid = int(parts[0])
                submit = float(parts[1])
                run = float(parts[3])
                req_procs = int(parts[7])
                if run <= 0: run = 1 # give it at least 1ms to avoid DIV/0
                prio = min(10, max(1, req_procs)) # proxy priority based on requested processors
                data.append({'pid': pid, 'arrivalTime': submit, 'priority': prio, 'processTime': int(run)})
                count += 1
                if count >= max_rows: break
            except ValueError:
                continue
    df = pd.DataFrame(data)
    if not df.empty:
        df.sort_values(by='arrivalTime', inplace=True)
        df['arrivalTime'] = df['arrivalTime'] - df['arrivalTime'].min()
    return df

def generate_datasets():
    datasets = {}
    n_processes = 200

    # 10 Real World Traces:
    datasets['Real SDSC SP2'] = load_swf('SDSC-SP2.swf', n_processes)
    datasets['Real SDSC BLUE'] = load_swf('SDSC-BLUE.swf', n_processes)
    datasets['Real ANL Intrepid'] = load_swf('ANL-Intrepid.swf', n_processes)
    datasets['Real CTC SP2'] = load_swf('CTC-SP2.swf', n_processes)
    datasets['Real HPC2N'] = load_swf('HPC2N.swf', n_processes)
    datasets['Real KTH SP2'] = load_swf('KTH-SP2.swf', n_processes)
    datasets['Real CEA Curie'] = load_swf('CEA-Curie.swf', n_processes)
    datasets['Real PIK IPLEX'] = load_swf('PIK-IPLEX.swf', n_processes)
    datasets['Real RICC'] = load_swf('RICC.swf', n_processes)
    datasets['Real Lublin'] = load_swf('Lublin-1024.swf', n_processes)

    # Note: excluding the synthetic ones entirely this time per user request. 
    return {k: v for k, v in datasets.items() if not v.empty}

def calculate_extended_metrics(df, total_time, quantum=None):
    df["TurnaroundTime"] = df["FinishTime"] - df["arrivalTime"]
    df["WaitingTime"] = df["TurnaroundTime"] - df["processTime"]
    df["ResponseTime"] = df["StartTime"] - df["arrivalTime"]
    
    metrics = {}
    metrics['AWT'] = df["WaitingTime"].mean()
    metrics['ATAT'] = df["TurnaroundTime"].mean()
    metrics['Response Time'] = df["ResponseTime"].mean()
    metrics['Bounded Slowdown'] = (df["TurnaroundTime"] / df["processTime"]).mean()
    metrics['Max Bounded Slowdown'] = (df["TurnaroundTime"] / df["processTime"]).max()
    metrics['WT Variance'] = df["WaitingTime"].var() if len(df) > 1 else 0
    metrics['WT CV'] = df["WaitingTime"].std() / df["WaitingTime"].mean() if df["WaitingTime"].mean() > 0 else 0
    metrics['MWT'] = df["WaitingTime"].max()
    metrics['Throughput'] = len(df) / total_time if total_time > 0 else 0
    
    total_burst = df["processTime"].sum()
    metrics['CPU Utilization (%)'] = (total_burst / total_time) * 100 if total_time > 0 else 0
    
    makespan = df["FinishTime"].max() - df["arrivalTime"].min()
    metrics['Makespan'] = makespan if makespan > 0 else 0
    metrics['Average Queue Length'] = (len(df) / makespan) * metrics['AWT'] if makespan > 0 else 0
    
    # 2. Resource waste/idle time
    first_arrival = df["arrivalTime"].min()
    idle_time = total_time - total_burst - first_arrival
    metrics['Idle Time'] = idle_time if idle_time > 0 else 0
    
    sum_wt = df["WaitingTime"].sum()
    sum_sq_wt = (df["WaitingTime"]**2).sum()
    n = len(df)
    metrics['JFI'] = (sum_wt**2) / (n * sum_sq_wt) if sum_sq_wt > 0 else 1.0
    
    def gini(array):
        array = np.sort(array)
        index = np.arange(1, array.shape[0] + 1)
        nn = array.shape[0]
        return (np.sum((2 * index - nn  - 1) * array)) / (nn * np.sum(array)) if np.sum(array) > 0 else 0
    metrics['Gini (WT)'] = gini(df["WaitingTime"].values)
    
    avg_burst = df["processTime"].mean()
    starvation_threshold = 3 * avg_burst
    metrics['Starvation Count'] = len(df[df["WaitingTime"] > starvation_threshold])
    metrics['Starvation Rate (%)'] = (metrics['Starvation Count'] / n) * 100 if n > 0 else 0
    
    # 1. Preemption frequency
    # 8. Dynamic task switching efficiency
    cs_count = len(df)
    if 'Preemptions' in df.columns:
        cs_count += df['Preemptions'].sum()
    metrics['Preemption Frequency'] = cs_count / n if n > 0 else 0
    
    # Assuming 0.1 time unit per context switch
    cs_overhead = 0.1 * cs_count
    metrics['Task Switching Eff (%)'] = (total_burst / (total_burst + cs_overhead)) * 100 if (total_burst + cs_overhead) > 0 else 0

    # 3. Priority inversion potential
    # If a high priority job arrived and is waiting while a lower priority job is executing
    inversion_count = 0
    # 5. Fairness bias / fairness to low-priority jobs
    # Correlation between priority and waiting time.
    # Higher priority (lower number in typical OS, but here we used min(10, req_procs), let's keep it straight metric-wise)
    # The higher the value of 'priority' column here, the higher the "priority".
    # A negative correlation means higher priority gets lower waiting time (fairness to priority, bias against low).
    
    if n > 0:
        for idx, row in df.iterrows():
            arr, prio = row['arrivalTime'], row['priority']
            # Find jobs with lower priority that were executing when this higher priority job arrived
            # This is simpler logic just evaluating temporal overlap
            if prio > 1:
                lower_prio_executing = df[(df['priority'] < prio) & (df['StartTime'] < arr) & (df['FinishTime'] > arr)]
                if not lower_prio_executing.empty:
                    inversion_count += len(lower_prio_executing)
                    
        metrics['Priority Inversion Potential'] = inversion_count
        
        # Pearson correlation
        std_prio = df['priority'].std()
        std_wt = df['WaitingTime'].std()
        if std_prio > 0 and std_wt > 0:
            metrics['Fairness Bias (Corr)'] = df['priority'].corr(df['WaitingTime'])
        else:
            metrics['Fairness Bias (Corr)'] = 0.0
            
    # 6. Fairness over time
    # Split the dataset into first half and second half temporally
    if n > 1:
        mid_time = first_arrival + (total_time - first_arrival) / 2
        df_first = df[df['arrivalTime'] <= mid_time]
        df_second = df[df['arrivalTime'] > mid_time]
        
        def safe_jfi(sub_df):
            if sub_df.empty: return 1.0
            s_wt = sub_df["WaitingTime"].sum()
            ss_wt = (sub_df["WaitingTime"]**2).sum()
            return (s_wt**2) / (len(sub_df) * ss_wt) if ss_wt > 0 else 1.0
            
        metrics['JFI First Half'] = safe_jfi(df_first)
        metrics['JFI Second Half'] = safe_jfi(df_second)
    else:
        metrics['JFI First Half'] = 1.0
        metrics['JFI Second Half'] = 1.0

    # 7. Throughput vs. fairness metric 
    # Ratio of Throughput to Gini Inequality index - higher is better performance-fairness balance
    gt = metrics['Gini (WT)']
    metrics['Throughput to Gini'] = metrics['Throughput'] / gt if gt > 0 else metrics['Throughput']

    # ===== NEW METRICS =====
    
    # 1. Normalized Turnaround Time (NTT) - Mean ratio of turnaround to service time
    metrics['NTT'] = (df["TurnaroundTime"] / df["processTime"]).mean()
    
    # 2. Percentile Metrics for Waiting Time and Response Time
    metrics['WT P90'] = np.percentile(df["WaitingTime"], 90)
    metrics['WT P95'] = np.percentile(df["WaitingTime"], 95)
    metrics['WT P99'] = np.percentile(df["WaitingTime"], 99)
    metrics['RT P90'] = np.percentile(df["ResponseTime"], 90)
    metrics['RT P95'] = np.percentile(df["ResponseTime"], 95)
    metrics['RT P99'] = np.percentile(df["ResponseTime"], 99)
    
    # 3. Load Imbalance Factor - Temporal variation in CPU usage
    # Split timeline into 10 windows and calculate CPU usage per window
    if makespan > 0 and n > 10:
        n_windows = 10
        window_size = makespan / n_windows
        window_utilizations = []
        for i in range(n_windows):
            window_start = first_arrival + i * window_size
            window_end = window_start + window_size
            # Count jobs executing during this window
            window_jobs = df[(df['StartTime'] < window_end) & (df['FinishTime'] > window_start)]
            window_cpu_time = 0
            for _, job in window_jobs.iterrows():
                overlap_start = max(job['StartTime'], window_start)
                overlap_end = min(job['FinishTime'], window_end)
                window_cpu_time += max(0, overlap_end - overlap_start)
            window_util = (window_cpu_time / window_size) * 100 if window_size > 0 else 0
            window_utilizations.append(window_util)
        metrics['Load Imbalance Factor'] = np.std(window_utilizations)
    else:
        metrics['Load Imbalance Factor'] = 0
    
    # 4. Convoy Effect Measure - Average delay caused by long jobs blocking short ones
    # Identify significantly long jobs (top 10%) and measure delay they cause to short jobs
    if n > 10:
        long_threshold = np.percentile(df["processTime"], 90)
        long_jobs = df[df["processTime"] >= long_threshold]
        short_jobs = df[df["processTime"] < long_threshold]
        
        convoy_delay = 0
        for _, short_job in short_jobs.iterrows():
            # Check if short job waited behind long jobs
            for _, long_job in long_jobs.iterrows():
                if (short_job['arrivalTime'] > long_job['arrivalTime'] and 
                    short_job['StartTime'] > long_job['StartTime'] and
                    short_job['StartTime'] < long_job['FinishTime']):
                    # Short job waited for long job
                    convoy_delay += min(long_job['FinishTime'] - short_job['StartTime'], 
                                       short_job['WaitingTime'])
        metrics['Convoy Effect'] = convoy_delay / len(short_jobs) if len(short_jobs) > 0 else 0
    else:
        metrics['Convoy Effect'] = 0
    
    # 5. Response Ratio - (Waiting Time + Service Time) / Service Time - Higher is worse
    df['ResponseRatio'] = (df['WaitingTime'] + df['processTime']) / df['processTime']
    metrics['Avg Response Ratio'] = df['ResponseRatio'].mean()
    metrics['Max Response Ratio'] = df['ResponseRatio'].max()
    
    # 6. Scheduling Overhead Percentage - Already calculated, adding explicit metric
    metrics['Scheduling Overhead (%)'] = (cs_overhead / total_time) * 100 if total_time > 0 else 0
    
    # 7. Weighted Turnaround Time - Weighted by priority (higher priority = more weight)
    priority_weights = df['priority'] / df['priority'].sum() if df['priority'].sum() > 0 else np.ones(n) / n
    metrics['Weighted TAT'] = (df['TurnaroundTime'] * priority_weights).sum()
    
    # 8. Fairness per Priority Class - Calculate JFI for each priority level
    unique_priorities = df['priority'].unique()
    if len(unique_priorities) > 1:
        priority_jfi_values = []
        for prio in unique_priorities:
            prio_jobs = df[df['priority'] == prio]
            if len(prio_jobs) > 1:
                p_sum_wt = prio_jobs["WaitingTime"].sum()
                p_sum_sq_wt = (prio_jobs["WaitingTime"]**2).sum()
                prio_jfi = (p_sum_wt**2) / (len(prio_jobs) * p_sum_sq_wt) if p_sum_sq_wt > 0 else 1.0
                priority_jfi_values.append(prio_jfi)
        metrics['Avg JFI Per Priority'] = np.mean(priority_jfi_values) if priority_jfi_values else 1.0
        metrics['Min JFI Per Priority'] = np.min(priority_jfi_values) if priority_jfi_values else 1.0
    else:
        metrics['Avg JFI Per Priority'] = metrics['JFI']
        metrics['Min JFI Per Priority'] = metrics['JFI']
    
    # 9. Time-Weighted Average Queue Depth - More accurate than Little's Law approximation
    if makespan > 0:
        # Calculate queue length at each event (arrival/completion)
        events = []
        for _, job in df.iterrows():
            events.append(('arrival', job['arrivalTime']))
            events.append(('start', job['StartTime']))
            events.append(('finish', job['FinishTime']))
        events.sort(key=lambda x: x[1])
        
        queue_depth = 0
        running = 0
        total_queue_time = 0
        prev_time = first_arrival
        
        for event_type, event_time in events:
            if event_time > prev_time:
                total_queue_time += queue_depth * (event_time - prev_time)
            
            if event_type == 'arrival':
                queue_depth += 1
            elif event_type == 'start':
                queue_depth -= 1
                running += 1
            elif event_type == 'finish':
                running -= 1
            
            prev_time = event_time
        
        metrics['Time-Weighted Queue Depth'] = total_queue_time / makespan if makespan > 0 else 0
    else:
        metrics['Time-Weighted Queue Depth'] = 0
    
    # 10. Predictability Score - Coefficient of variation of normalized turnaround time
    # Lower is better (more predictable)
    ntt_array = df["TurnaroundTime"] / df["processTime"]
    metrics['Predictability CV'] = ntt_array.std() / ntt_array.mean() if ntt_array.mean() > 0 else 0
    
    # 11. Stretch Factor (similar to NTT but sometimes defined differently in literature)
    metrics['Avg Stretch'] = ntt_array.mean()
    metrics['Max Stretch'] = ntt_array.max()
    
    # 12. Service Time Statistics
    metrics['Service Time Mean'] = df["processTime"].mean()
    metrics['Service Time Median'] = df["processTime"].median()
    metrics['Service Time Std'] = df["processTime"].std()
    metrics['Service Time CV'] = df["processTime"].std() / df["processTime"].mean() if df["processTime"].mean() > 0 else 0
    
    # 13. Arrival Rate Statistics
    if makespan > 0:
        metrics['Arrival Rate'] = n / makespan
        inter_arrival_times = df['arrivalTime'].diff().dropna()
        if len(inter_arrival_times) > 0:
            metrics['Inter-Arrival Mean'] = inter_arrival_times.mean()
            metrics['Inter-Arrival CV'] = inter_arrival_times.std() / inter_arrival_times.mean() if inter_arrival_times.mean() > 0 else 0
        else:
            metrics['Inter-Arrival Mean'] = 0
            metrics['Inter-Arrival CV'] = 0
    else:
        metrics['Arrival Rate'] = 0
        metrics['Inter-Arrival Mean'] = 0
        metrics['Inter-Arrival CV'] = 0
    
    # 14. Size-based Fairness - Gini coefficient for different job size categories
    if n > 10:
        # Divide jobs into small, medium, large based on process time
        small_threshold = np.percentile(df["processTime"], 33)
        large_threshold = np.percentile(df["processTime"], 67)
        
        small_jobs_wt = df[df["processTime"] <= small_threshold]["WaitingTime"]
        large_jobs_wt = df[df["processTime"] >= large_threshold]["WaitingTime"]
        
        metrics['Small Jobs Avg WT'] = small_jobs_wt.mean() if len(small_jobs_wt) > 0 else 0
        metrics['Large Jobs Avg WT'] = large_jobs_wt.mean() if len(large_jobs_wt) > 0 else 0
        metrics['Size Fairness Ratio'] = (small_jobs_wt.mean() / large_jobs_wt.mean()) if len(large_jobs_wt) > 0 and large_jobs_wt.mean() > 0 else 1.0
    else:
        metrics['Small Jobs Avg WT'] = metrics['AWT']
        metrics['Large Jobs Avg WT'] = metrics['AWT']
        metrics['Size Fairness Ratio'] = 1.0

    return metrics

def fcfs_schedule(df_in):
    df = df_in.copy().sort_values(by='arrivalTime').reset_index(drop=True)
    current_time = 0
    start_times, finish_times = [], []
    for arr, burst in zip(df['arrivalTime'], df['processTime']):
        start = max(current_time, arr)
        start_times.append(start)
        finish = start + burst
        finish_times.append(finish)
        current_time = finish
    df['StartTime'] = start_times
    df['FinishTime'] = finish_times
    df['Preemptions'] = 0
    return df, current_time

def priority_schedule(df_in): 
    # Non-preemptive, higher number = higher priority
    df = df_in.copy().sort_values(by=['arrivalTime', 'priority'], ascending=[True, False]).reset_index(drop=True)
    ready_queue = []
    current_time = 0
    completed = 0
    n = len(df)
    
    start_times = np.zeros(n)
    finish_times = np.zeros(n)
    is_completed = np.zeros(n, dtype=bool)
    
    while completed < n:
        arrived = df[(df['arrivalTime'] <= current_time) & (~is_completed)]
        if arrived.empty:
            next_arrival = df.loc[~is_completed, 'arrivalTime'].min()
            current_time = next_arrival
            arrived = df[(df['arrivalTime'] <= current_time) & (~is_completed)]
            
        # Pick highest priority
        idx = arrived['priority'].idxmax()
        start = current_time
        burst = df.loc[idx, 'processTime']
        finish = start + burst
        
        start_times[idx] = start
        finish_times[idx] = finish
        is_completed[idx] = True
        
        current_time = finish
        completed += 1
        
    df['StartTime'] = start_times
    df['FinishTime'] = finish_times
    df['Preemptions'] = 0
    return df, current_time

def sjf_schedule(df_in):
    # Non-preemptive Shortest Job First
    df = df_in.copy().sort_values(by=['arrivalTime', 'processTime']).reset_index(drop=True)
    current_time = 0
    completed = 0
    n = len(df)
    
    start_times = np.zeros(n)
    finish_times = np.zeros(n)
    is_completed = np.zeros(n, dtype=bool)
    
    while completed < n:
        arrived = df[(df['arrivalTime'] <= current_time) & (~is_completed)]
        if arrived.empty:
            next_arrival = df.loc[~is_completed, 'arrivalTime'].min()
            current_time = next_arrival
            arrived = df[(df['arrivalTime'] <= current_time) & (~is_completed)]
            
        # Pick shortest burst time
        idx = arrived['processTime'].idxmin()
        start = current_time
        burst = df.loc[idx, 'processTime']
        finish = start + burst
        
        start_times[idx] = start
        finish_times[idx] = finish
        is_completed[idx] = True
        
        current_time = finish
        completed += 1
        
    df['StartTime'] = start_times
    df['FinishTime'] = finish_times
    df['Preemptions'] = 0
    return df, current_time

def priority_aging_schedule(df_in): 
    # Non-preemptive Priority with Aging
    df = df_in.copy().sort_values(by=['arrivalTime', 'priority'], ascending=[True, False]).reset_index(drop=True)
    current_time = 0
    completed = 0
    n = len(df)
    
    start_times = np.zeros(n)
    finish_times = np.zeros(n)
    is_completed = np.zeros(n, dtype=bool)
    
    # Priority increases by 1 for roughly every 10x mean burst waiting time
    aging_interval = df['processTime'].mean() * 10 
    if aging_interval <= 0: aging_interval = 1000
    
    while completed < n:
        arrived = df[(df['arrivalTime'] <= current_time) & (~is_completed)].copy()
        if arrived.empty:
            next_arrival = df.loc[~is_completed, 'arrivalTime'].min()
            current_time = next_arrival
            arrived = df[(df['arrivalTime'] <= current_time) & (~is_completed)].copy()
            
        # Dynamic priority = base priority + aging factor
        arrived['dynamic_priority'] = arrived['priority'] + ((current_time - arrived['arrivalTime']) / aging_interval)
        
        # Pick highest dynamic priority
        idx = arrived['dynamic_priority'].idxmax()
        start = current_time
        burst = df.loc[idx, 'processTime']
        finish = start + burst
        
        start_times[idx] = start
        finish_times[idx] = finish
        is_completed[idx] = True
        
        current_time = finish
        completed += 1
        
    df['StartTime'] = start_times
    df['FinishTime'] = finish_times
    df['Preemptions'] = 0
    return df, current_time


def round_robin_schedule(df_in, quantum):
    df = df_in.copy().sort_values(by='arrivalTime').reset_index(drop=True)
    n = len(df)
    remaining_burst = df['processTime'].values.copy()
    start_times = np.full(n, -1.0)
    finish_times = np.zeros(n)
    preemptions = np.zeros(n)
    
    current_time = 0
    completed = 0
    queue = []
    
    idx_arrived = 0
    
    while completed < n:
        while idx_arrived < n and df.loc[idx_arrived, 'arrivalTime'] <= current_time:
            queue.append(idx_arrived)
            idx_arrived += 1
            
        if not queue:
            current_time = df.loc[idx_arrived, 'arrivalTime']
            continue
            
        curr_proc = queue.pop(0)
        if start_times[curr_proc] == -1:
            start_times[curr_proc] = current_time
            
        time_to_run = min(quantum, remaining_burst[curr_proc])
        current_time += time_to_run
        remaining_burst[curr_proc] -= time_to_run
        
        while idx_arrived < n and df.loc[idx_arrived, 'arrivalTime'] <= current_time:
            queue.append(idx_arrived)
            idx_arrived += 1
            
        if remaining_burst[curr_proc] == 0:
            finish_times[curr_proc] = current_time
            completed += 1
        else:
            queue.append(curr_proc)
            preemptions[curr_proc] += 1
            
    df['StartTime'] = start_times
    df['FinishTime'] = finish_times
    df['Preemptions'] = preemptions
    return df, current_time

def run_analysis():
    datasets = generate_datasets()
    all_results = []
    
    # To store data for 9. Job-wait distribution
    all_job_waits = []
    
    for ds_name, ds_df in datasets.items():
        mean_burst = ds_df['processTime'].mean()
        quantum = int(mean_burst / 2) if int(mean_burst / 2) > 0 else 1
        
        # FCFS
        res_fcfs, tt_fcfs = fcfs_schedule(ds_df)
        m_fcfs = calculate_extended_metrics(res_fcfs, tt_fcfs)
        m_fcfs['Algorithm'] = 'FCFS'
        m_fcfs['Dataset'] = ds_name
        
        # Priority
        res_prio, tt_prio = priority_schedule(ds_df)
        m_prio = calculate_extended_metrics(res_prio, tt_prio)
        m_prio['Algorithm'] = 'Priority'
        m_prio['Dataset'] = ds_name
        
        # Round Robin
        res_rr, tt_rr = round_robin_schedule(ds_df, quantum)
        m_rr = calculate_extended_metrics(res_rr, tt_rr, quantum)
        m_rr['Algorithm'] = 'Round Robin'
        m_rr['Dataset'] = ds_name
        
        # SJF
        res_sjf, tt_sjf = sjf_schedule(ds_df)
        m_sjf = calculate_extended_metrics(res_sjf, tt_sjf)
        m_sjf['Algorithm'] = 'SJF'
        m_sjf['Dataset'] = ds_name

        # Priority (Aging)
        res_prio_aging, tt_prio_aging = priority_aging_schedule(ds_df)
        m_prio_aging = calculate_extended_metrics(res_prio_aging, tt_prio_aging)
        m_prio_aging['Algorithm'] = 'Priority (Aging)'
        m_prio_aging['Dataset'] = ds_name
        
        all_results.extend([m_fcfs, m_prio, m_rr, m_sjf, m_prio_aging])
        
        # Save raw waiting times for the Job-wait distribution plot
        for _, row in res_fcfs.iterrows():
            all_job_waits.append({'Dataset': ds_name, 'Algorithm': 'FCFS', 'WaitingTime': row['WaitingTime']})
        for _, row in res_prio.iterrows():
            all_job_waits.append({'Dataset': ds_name, 'Algorithm': 'Priority', 'WaitingTime': row['WaitingTime']})
        for _, row in res_rr.iterrows():
             all_job_waits.append({'Dataset': ds_name, 'Algorithm': 'Round Robin', 'WaitingTime': row['WaitingTime']})
        for _, row in res_sjf.iterrows():
             all_job_waits.append({'Dataset': ds_name, 'Algorithm': 'SJF', 'WaitingTime': row['WaitingTime']})
        for _, row in res_prio_aging.iterrows():
             all_job_waits.append({'Dataset': ds_name, 'Algorithm': 'Priority (Aging)', 'WaitingTime': row['WaitingTime']})
        
    results_df = pd.DataFrame(all_results)
    
    # Generate Plots
    metrics_to_plot = [
        'AWT', 'Response Time', 'Bounded Slowdown', 'Max Bounded Slowdown', 'WT Variance', 'WT CV', 'JFI', 'Starvation Rate (%)', 
        'Makespan', 'Average Queue Length', 'MWT', 'Preemption Frequency', 'Priority Inversion Potential',
        'Fairness Bias (Corr)', 'Throughput to Gini', 'Task Switching Eff (%)',
        # New metrics
        'NTT', 'WT P95', 'RT P95', 'Load Imbalance Factor', 'Convoy Effect', 'Avg Response Ratio',
        'Weighted TAT', 'Avg JFI Per Priority', 'Time-Weighted Queue Depth', 'Predictability CV',
        'Avg Stretch', 'Service Time CV', 'Inter-Arrival CV', 'Size Fairness Ratio'
    ]
    
    if not os.path.exists("images"):
        os.makedirs("images")
        
    for metric in metrics_to_plot:
        plt.figure(figsize=(14, 8))
        sns.barplot(data=results_df, x='Dataset', y=metric, hue='Algorithm')
        plt.title(f'{metric} Comparison across Datasets')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(f'images/{metric.replace(" ", "_").replace("%", "Pct").replace("(", "").replace(")", "")}.png')
        plt.close()
        
    # Plot 6. Fairness over time (JFI First vs Second Half)
    time_df = pd.melt(results_df, id_vars=['Dataset', 'Algorithm'], value_vars=['JFI First Half', 'JFI Second Half'], 
                      var_name='Time_Period', value_name='JFI_Value')
    plt.figure(figsize=(14, 8))
    sns.catplot(data=time_df, x='Dataset', y='JFI_Value', hue='Algorithm', col='Time_Period', kind='bar', height=6, aspect=1.2)
    plt.tight_layout()
    plt.savefig('images/Fairness_Over_Time.png')
    plt.close('all')
        
    # Plot 9. Job-wait distribution
    waits_df = pd.DataFrame(all_job_waits)
    plt.figure(figsize=(14, 8))
    # Using log scale to better visualize distributions since AWT can be insanely high in HPC
    waits_df['LogWaitingTime'] = np.log1p(waits_df['WaitingTime'])
    sns.violinplot(data=waits_df, x='Dataset', y='LogWaitingTime', hue='Algorithm', split=False, cut=0)
    plt.title('Job-Wait Distribution (Log Scale) across Datasets')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig('images/Job_Wait_Distribution.png')
    plt.close()
        
    results_df.to_csv("results.csv", index=False)
    print(f"Analysis finished successfully on {len(datasets)} explicit real-world datasets. Saved images and CSV.")

if __name__ == "__main__":
    run_analysis()
