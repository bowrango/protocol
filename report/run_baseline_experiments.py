#!/usr/bin/env python3
"""
Run stop-and-go baseline experiments and save results to JSON.
Usage: python3 run_experiments.py
"""

import subprocess, time, os, re, tempfile, shutil, json, statistics, sys

PYTHON        = 'python3'
REPORT_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR      = os.path.dirname(REPORT_DIR)   # project root (one level up)
EMULATOR_PATH = os.path.join(BASE_DIR, 'Emulator', 'emulator.py')
SNG_SENDER    = os.path.join(BASE_DIR, 'src', 'baseline', 'sender_stop_and_go.py')
SNG_RECEIVER  = os.path.join(BASE_DIR, 'src', 'baseline', 'receiver_stop_and_go.py')
LARGE_FILE    = os.path.join(BASE_DIR, 'data', 'to_send_large.txt')


def create_config(tmpdir, bandwidth, drop_prob, reorder_prob, window_size=1):
    path = os.path.join(tmpdir, 'config.ini')
    with open(path, 'w') as f:
        f.write(f"""[emulator]
log_file={tmpdir}/emulator.log
port=8000

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
port=8001
window_size={window_size}
log_file={tmpdir}/sender_monitor.log

[receiver]
id=2
host=localhost
port=8002
write_location={tmpdir}/received.txt
log_file={tmpdir}/receiver_monitor.log
""")
    return path


def kill_ports():
    for port in [8000, 8001, 8002]:
        os.system(f"lsof -t -i:{port} 2>/dev/null | xargs kill -9 2>/dev/null || true")
    time.sleep(0.8)


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


def run_one(sender, receiver, config_path, run_timeout=900):
    tmpdir = os.path.dirname(config_path)
    emu  = subprocess.Popen([PYTHON, EMULATOR_PATH, config_path],
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
        print(f'    TIMED OUT after {run_timeout}s', flush=True)
        return None, None
    return parse_sender_log(os.path.join(tmpdir, 'sender_monitor.log'))


def run_n(n, sender, receiver, bandwidth, drop, reorder, window=1, run_timeout=900, label=''):
    goodputs, overheads = [], []
    for i in range(n):
        kill_ports()
        tmpdir = tempfile.mkdtemp(prefix='lab3_')
        try:
            cfg = create_config(tmpdir, bandwidth, drop, reorder, window)
            print(f'  [{label}] run {i+1}/{n} ... ', end='', flush=True)
            g, o = run_one(sender, receiver, cfg, run_timeout)
            if g is not None:
                goodputs.append(g)
                overheads.append(o or 0.0)
                print(f'goodput={g:.1f} B/s  overhead={o:.1f}%', flush=True)
            else:
                print('FAILED', flush=True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        time.sleep(1.5)
    return goodputs, overheads


def mean_std(vals):
    if not vals:
        return None, None
    m = statistics.mean(vals)
    s = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return m, s


def save_results(results):
    out_path = os.path.join(REPORT_DIR, 'experiment_results.json')
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'  -> Saved to {out_path}', flush=True)


if __name__ == '__main__':
    N = 5
    # Load any previously saved results so we can resume
    out_path = os.path.join(REPORT_DIR, 'experiment_results.json')
    if os.path.exists(out_path):
        with open(out_path) as f:
            results = json.load(f)
        print(f'Resuming from existing {out_path}')
    else:
        results = {}

    # Stop-and-go at 3 bandwidths: 2% drop, 2% reorder
    for bw, label, timeout in [
        (200000, '200k', 300),
        (20000,  '20k',  400),
        (2000,   '2k',   900),
    ]:
        key = f'sng_{label}'
        if key in results and results[key].get('goodput_mean') is not None:
            print(f'\nSkipping {key} — already in results file.', flush=True)
            continue
        print(f'\n=== Stop-and-Go  BW={label}  drop=2%  reorder=2% ===', flush=True)
        g, o = run_n(N, SNG_SENDER, SNG_RECEIVER,
                     bandwidth=bw, drop=0.02, reorder=0.02,
                     run_timeout=timeout, label=f'SNG-{label}')
        gm, gs = mean_std(g)
        om, os_ = mean_std(o)
        results[key] = {
            'goodput_mean': gm, 'goodput_std': gs,
            'overhead_mean': om, 'overhead_std': os_,
            'raw_goodput': g, 'raw_overhead': o,
        }
        save_results(results)  # save after each bandwidth group

    print('\n=== FINAL SUMMARY ===')
    for key, val in results.items():
        gm, gs = val['goodput_mean'], val['goodput_std']
        om, os_ = val['overhead_mean'], val['overhead_std']
        if gm is not None:
            print(f'{key}: goodput={gm:.0f}[{gs:.0f}]  overhead={om:.1f}%[{os_:.1f}%]')
        else:
            print(f'{key}: NO DATA')
