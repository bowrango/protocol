#!/usr/bin/env python3
"""
Run all custom-protocol experiments in parallel using different port ranges.
Three groups run concurrently:
  Group 1 (ports 8000-8002): Window-size sweep
  Group 2 (ports 8010-8012): Custom sensitivity
  Group 3 (ports 8020-8022): SNG sensitivity

Results are merged into experiment_results.json.
Usage: python3 run_experiments_parallel.py
"""

import subprocess, time, os, re, tempfile, shutil, json, statistics, sys, copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

PYTHON        = 'python3'
REPORT_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR      = os.path.dirname(REPORT_DIR)
EMULATOR_PATH = os.path.join(BASE_DIR, 'Emulator', 'emulator.py')

CUSTOM_SENDER   = os.path.join(BASE_DIR, 'src', 'custom', 'sender.py')
CUSTOM_RECEIVER = os.path.join(BASE_DIR, 'src', 'custom', 'receiver.py')
SNG_SENDER      = os.path.join(BASE_DIR, 'src', 'baseline', 'sender_stop_and_go.py')
SNG_RECEIVER    = os.path.join(BASE_DIR, 'src', 'baseline', 'receiver_stop_and_go.py')
LARGE_FILE      = os.path.join(BASE_DIR, 'data', 'to_send_large.txt')

# Lock for printing and results file
print_lock = threading.Lock()
results_lock = threading.Lock()


def create_config(tmpdir, bandwidth, drop_prob, reorder_prob, window_size, port_base):
    emu_port = port_base
    sender_port = port_base + 1
    receiver_port = port_base + 2
    path = os.path.join(tmpdir, 'config.ini')
    with open(path, 'w') as f:
        f.write(f"""[emulator]
log_file={tmpdir}/emulator.log
port={emu_port}

[network]
PROP_DELAY=0.100
MAX_PACKET_SIZE=1024
LINK_BANDWIDTH={bandwidth}
MAX_PACKETS_QUEUED=1000
DROP_MODEL=1
RANDOM_DROP_PROBABILITY={drop_prob}
REORDER_PROBABILITY={reorder_prob}

[nodes]
config_headers=sender,receiver
file_to_send={LARGE_FILE}

[sender]
id=1
host=localhost
port={sender_port}
window_size={window_size}
log_file={tmpdir}/sender_monitor.log

[receiver]
id=2
host=localhost
port={receiver_port}
write_location={tmpdir}/received.txt
log_file={tmpdir}/receiver_monitor.log
""")
    return path


def kill_ports(port_base):
    for port in [port_base, port_base + 1, port_base + 2]:
        os.system(f"lsof -t -i:{port} 2>/dev/null | xargs kill -9 2>/dev/null || true")
    time.sleep(0.5)


def parse_sender_log(log_path):
    try:
        content = open(log_path).read()
    except FileNotFoundError:
        return None, None
    goodput = overhead_pct = None
    m = re.search(r'Goodput\s*:\s*([\d.]+)', content)
    if m:
        goodput = float(m.group(1))
    mf = re.search(r'File Size\s*:\s*(\d+)', content)
    mo = re.search(r'Overhead\s*:\s*(\d+)', content)
    if mf and mo:
        fs, oh = int(mf.group(1)), int(mo.group(1))
        if fs > 0:
            overhead_pct = oh / fs * 100.0
    return goodput, overhead_pct


def run_one(sender, receiver, config_path, port_base, run_timeout=300):
    tmpdir = os.path.dirname(config_path)
    emu = subprocess.Popen([PYTHON, EMULATOR_PATH, config_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.6)
    recv = subprocess.Popen([PYTHON, receiver, config_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.4)
    send = subprocess.Popen([PYTHON, sender, config_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        send.wait(timeout=run_timeout)
        recv.wait(timeout=30)
        emu.wait(timeout=10)
    except subprocess.TimeoutExpired:
        for p in [send, recv, emu]:
            try: p.kill()
            except: pass
        return None, None
    return parse_sender_log(os.path.join(tmpdir, 'sender_monitor.log'))


def run_n(n, sender, receiver, bandwidth, drop, reorder, window,
          port_base, run_timeout=300, label=''):
    goodputs, overheads = [], []
    for i in range(n):
        kill_ports(port_base)
        tmpdir = tempfile.mkdtemp(prefix='lab3_par_')
        try:
            cfg = create_config(tmpdir, bandwidth, drop, reorder, window, port_base)
            with print_lock:
                print(f'  [{label}] run {i+1}/{n} ... ', end='', flush=True)
            g, o = run_one(sender, receiver, cfg, port_base, run_timeout)
            if g is not None:
                goodputs.append(g)
                overheads.append(o or 0.0)
                with print_lock:
                    print(f'goodput={g:.1f} B/s  overhead={o:.1f}%', flush=True)
            else:
                with print_lock:
                    print('FAILED', flush=True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        time.sleep(1.0)
    return goodputs, overheads


def mean_std(vals):
    if not vals:
        return None, None
    m = statistics.mean(vals)
    s = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return m, s


def entry(g, o):
    gm, gs = mean_std(g)
    om, os_ = mean_std(o)
    return {
        'goodput_mean': gm, 'goodput_std': gs,
        'overhead_mean': om, 'overhead_std': os_,
        'raw_goodput': g, 'raw_overhead': o,
    }


def load_results():
    path = os.path.join(REPORT_DIR, 'experiment_results.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_results(results):
    path = os.path.join(REPORT_DIR, 'experiment_results.json')
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)


def merge_result(key, data):
    with results_lock:
        results = load_results()
        results[key] = data
        save_results(results)


# ================================================================
# Experiment groups
# ================================================================

def group_window_sweep(N, port_base):
    """Group 1: Window-size sweep at BW=200k, 2% loss, 2% reorder."""
    existing = load_results()
    for w in [1, 5, 10, 20, 40]:
        key = f'custom_w{w}'
        if key in existing and existing[key].get('goodput_mean') is not None:
            with print_lock:
                print(f'  Skipping {key} — already in results.', flush=True)
            continue
        with print_lock:
            print(f'\n=== [G1] Custom W={w}  BW=200k  2%/2% ===', flush=True)
        g, o = run_n(N, CUSTOM_SENDER, CUSTOM_RECEIVER,
                     bandwidth=200000, drop=0.02, reorder=0.02,
                     window=w, port_base=port_base, run_timeout=300,
                     label=f'G1:W={w}')
        merge_result(key, entry(g, o))

    # Determine best window and alias as custom_200k
    results = load_results()
    best_w = max([1, 5, 10, 20, 40],
                 key=lambda w: (results.get(f'custom_w{w}', {}).get('goodput_mean') or 0))
    with print_lock:
        print(f'\n  Best window: W={best_w}', flush=True)
    merge_result('custom_200k', copy.deepcopy(results[f'custom_w{best_w}']))
    return best_w


def group_custom_sensitivity(N, port_base, best_w):
    """Group 2: Custom protocol sensitivity (3 loss/reorder configs)."""
    existing = load_results()
    for drop, reorder, tag in [(0.05, 0.05, '5pct'), (0.02, 0.02, '2pct'), (0.0, 0.0, '0pct')]:
        key = f'custom_sens_{tag}'
        if key in existing and existing[key].get('goodput_mean') is not None:
            with print_lock:
                print(f'  Skipping {key} — already in results.', flush=True)
            continue
        with print_lock:
            print(f'\n=== [G2] Custom sens {tag}  W={best_w} ===', flush=True)
        g, o = run_n(N, CUSTOM_SENDER, CUSTOM_RECEIVER,
                     bandwidth=200000, drop=drop, reorder=reorder,
                     window=best_w, port_base=port_base, run_timeout=300,
                     label=f'G2:Cust-{tag}')
        merge_result(key, entry(g, o))


def group_sng_sensitivity(N, port_base):
    """Group 3: Stop-and-Go sensitivity (3 loss/reorder configs)."""
    existing = load_results()
    for drop, reorder, tag in [(0.05, 0.05, '5pct'), (0.02, 0.02, '2pct'), (0.0, 0.0, '0pct')]:
        key = f'sng_sens_{tag}'
        if key in existing and existing[key].get('goodput_mean') is not None:
            with print_lock:
                print(f'  Skipping {key} — already in results.', flush=True)
            continue
        with print_lock:
            print(f'\n=== [G3] SNG sens {tag} ===', flush=True)
        g, o = run_n(N, SNG_SENDER, SNG_RECEIVER,
                     bandwidth=200000, drop=drop, reorder=reorder,
                     window=1, port_base=port_base, run_timeout=300,
                     label=f'G3:SNG-{tag}')
        merge_result(key, entry(g, o))


if __name__ == '__main__':
    N = 5

    # Group 1 must finish first so we know best_w for Group 2
    print('=' * 60)
    print('PHASE 1: Window sweep (sequential — need best W for phase 2)')
    print('=' * 60)
    best_w = group_window_sweep(N, port_base=8000)

    # Groups 2 & 3 can run in parallel (different ports)
    print('\n' + '=' * 60)
    print(f'PHASE 2: Sensitivity tests in parallel (best W={best_w})')
    print('=' * 60)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_custom = executor.submit(group_custom_sensitivity, N, 8010, best_w)
        f_sng    = executor.submit(group_sng_sensitivity, N, 8020)
        for future in as_completed([f_custom, f_sng]):
            exc = future.exception()
            if exc:
                print(f'ERROR: {exc}', flush=True)

    # Final summary
    results = load_results()
    print('\n' + '=' * 60)
    print('ALL EXPERIMENTS COMPLETE')
    print('=' * 60)
    for key in sorted(results.keys()):
        val = results[key]
        gm = val.get('goodput_mean')
        gs = val.get('goodput_std')
        om = val.get('overhead_mean')
        os_ = val.get('overhead_std')
        if gm is not None:
            print(f'  {key:25s}: goodput={gm:8.0f}[{gs:6.0f}]  overhead={om:5.1f}%[{os_:4.1f}%]')
        else:
            print(f'  {key:25s}: NO DATA')

    print(f'\nBest window: W={best_w}')
    print('Next steps:')
    print(f'  cd {REPORT_DIR}')
    print(f'  {PYTHON} generate_latex_results.py')
    print(f'  {PYTHON} generate_plots.py')
