#!/usr/bin/env python3
"""
Generate variance bar-charts from experiment_results.json.
Saves figures/goodput_variance.pdf and figures/overhead_variance.pdf.
Usage: /Users/mattbowring/Desktop/dlopt/.venv/bin/python3 generate_plots.py
"""

import json, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
JSON_PATH  = os.path.join(BASE_DIR, 'experiment_results.json')
FIG_DIR    = os.path.join(BASE_DIR, 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

with open(JSON_PATH) as f:
    results = json.load(f)


def bar_chart(sng_vals, custom_vals, ylabel, title, filename,
              sng_label='Stop-and-Go', custom_label='Custom Protocol'):
    """Draw a grouped bar chart: each run side by side for both protocols."""
    n = max(len(sng_vals), len(custom_vals))
    x = np.arange(1, n + 1)
    width = 0.35

    fig, ax = plt.subplots(figsize=(7, 4))

    if sng_vals:
        ax.bar(x[:len(sng_vals)] - width / 2, sng_vals, width,
               label=sng_label, color='steelblue', edgecolor='black', linewidth=0.6)
    if custom_vals:
        ax.bar(x[:len(custom_vals)] + width / 2, custom_vals, width,
               label=custom_label, color='tomato', edgecolor='black', linewidth=0.6)

    # Mean lines
    if sng_vals:
        ax.axhline(np.mean(sng_vals), color='steelblue', linestyle='--',
                   linewidth=1.2, label=f'{sng_label} mean')
    if custom_vals:
        ax.axhline(np.mean(custom_vals), color='tomato', linestyle='--',
                   linewidth=1.2, label=f'{custom_label} mean')

    ax.set_xlabel('Run')
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.legend(fontsize=8)
    ax.grid(axis='y', linestyle=':', alpha=0.7)
    fig.tight_layout()
    path = os.path.join(FIG_DIR, filename)
    fig.savefig(path)
    print(f'Saved {path}')
    plt.close(fig)


# ---- Goodput chart ----
sng_goodput    = results.get('sng_200k', {}).get('raw_goodput') or []
custom_goodput = results.get('custom_200k', {}).get('raw_goodput') or []
bar_chart(sng_goodput, custom_goodput,
          ylabel='Goodput (bytes/s)',
          title='Goodput per run — BW=200k, 2% loss, 2% reorder',
          filename='goodput_variance.pdf')

# ---- Overhead chart ----
sng_overhead    = results.get('sng_200k', {}).get('raw_overhead') or []
custom_overhead = results.get('custom_200k', {}).get('raw_overhead') or []
bar_chart(sng_overhead, custom_overhead,
          ylabel='Overhead (% of bytes sent)',
          title='Overhead per run — BW=200k, 2% loss, 2% reorder',
          filename='overhead_variance.pdf')

print('Done.')
