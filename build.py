"""Build the offline Reviewer Model Benchmark page from local benchmark-results.json."""

import argparse
import hashlib
import colorsys
import html
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from stats import (V2_SCORING_VERSION, V2_SPEED_KEYS, EFFORTS, HARNESS_NAMES, MODEL_NAMES, REVIEWERS, SCORING_VERSION, SPEED_KEYS,
                   TOKEN_KEYS,
                   extract, extract_v2, load_pricing, plan_weekly_api_usd, plan_weekly_cost)


V1_SPEED_KEYS = SPEED_KEYS
PAGE_VERSION = "2.6.3"
V2_PAGE_VERSION = "3.0.0"
# Model colors in MODEL_NAMES order (stats.py); series follow harness order, then this model order.
MODEL_COLORS = {
    "gpt-6.1-sol": "#4c78b8",
    "gpt-6.2-sol": "#4c78b8",
    "gpt-6.1-terra": "#3a9ab8",
    "gemini-4-neon": "#8a6bd7",
    "deepseek-v4.1-flash": "#d07849",
    "glm-5.3": "#a8a037",
    "gpt-6-luna": "#b47627",
    "opus": "#8659b9",
    "sonnet": "#bb5272",
    "haiku": "#198f76",
    "gemini-4-hydrogen": "#6b7fd7",
    "deepseek-flash": "#d07849",
    "strata-iq3_xxs": "#2f8fa9",
}
TOKEN_COLORS = {"uncachedInput": "#6388b7", "cachedInput": "#5f9e98", "output": "#b3935e"}
# Marker symbols per harness (names in stats.py); all effort lines are solid.
HARNESS_SYMBOLS = {"codex": "circle", "claude-code": "diamond", "antigravity": "square"}
HARNESS_COLOR = "#9a958c"
ROLE_COLORS = ("#6388b7", "#5f9e98", "#b3935e", "#9b7fb5")
CHART_TEXT = "#5c5e5c"
CHART_PLOT = "#f8f5ef"
CHART_GRID = "#eae3d9"
CHART_FONT = "Source Sans 3, Source Han Sans, sans-serif"
PARETO_COLOR = "#e6aa00"
LEGEND_GAP = " " * 10

BRAND_ICON_PATHS = '''
<path fill-rule="nonzero" d="M0 53v1813.33h1386.67v-320H1280v213.34H106.667V159.667H1280V373h106.67V53z"/>
<path d="M260 420h620v72H260z M260 610h500v72H260z M260 800h430v72H260z M260 990h360v72H260z"/>
<path fill-rule="evenodd" d="M1226.67 1439.67c113.33 0 217.48-39.28 299.6-104.96l302.37 302.65c20.82 20.84 54.59 20.85 75.42.04 20.84-20.82 20.86-54.59.04-75.43l-302.41-302.68c65.7-82.12 104.98-186.29 104.98-299.623 0-265.097-214.91-480-480-480-265.1 0-480.003 214.903-480.003 480 0 265.093 214.903 480.003 480.003 480.003Zm0-106.67c206.18 0 373.33-167.15 373.33-373.333 0-206.187-167.15-373.334-373.33-373.334-206.19 0-373.337 167.147-373.337 373.334 0 206.183 167.147 373.333 373.337 373.333Z"/>
'''
FAVICON_COLOR = "#805e38"

ICON_SHAPES = {
    "standards": '<path d="m8 5-6 7 6 7m8-14 6 7-6 7M14 2 10 22" stroke-width="2.5"/>',
    "spec": '<path d="M5 2h10l4 4v16H5Z" fill="currentColor" stroke="none"/><path d="M15 2v5h4M8 12h8m-8 4h8m-8 4h5" stroke="#fffefa" stroke-width="1.7"/>',
    "audit": '<path d="M12 2 21 5v6c0 5.2-3.5 8.6-9 11-5.5-2.4-9-5.8-9-11V5Z" fill="currentColor" stroke="none"/><path d="M5 6.2 12 3.8V12H5V6.2Zm7 5.8h7.7c-.5 3.6-3.1 6.4-7.7 8.6V12Z" fill="#fffefa" stroke="none"/><path d="M12 3v17M4 12h16" stroke-width="1"/>',
    "readiness": '<path d="M3 4h3v3H3Zm6 .3h12v2.4H9ZM3 10.5h3v3H3Zm6 .3h12v2.4H9ZM3 17h3v3H3Zm6 .3h12v2.4H9Z" fill="currentColor" stroke="none"/>',
    "external": '<path d="M5 19 19 5M9 5h10v10"/>',
}

SUMMARY_ICON_SHAPES = {
    "models": ("0 0 48 48", '''
<path d="M44,33H36a2,2,0,0,0-2,2v2c-4.7-.4-7.9-3.5-7.9-7.9v-9A13,13,0,0,0,14,7.1V5a2,2,0,0,0-2-2H4A2,2,0,0,0,2,5v8a2,2,0,0,0,2,2h8a2,2,0,0,0,2-2V11.1a9,9,0,0,1,8.1,9v9c0,6.6,5,11.4,11.9,11.9v2a2,2,0,0,0,2,2h8a2,2,0,0,0,2-2V35A2,2,0,0,0,44,33ZM10,11H6V7h4ZM42,41H38V37h4Z"/>
<path d="M44,3H36a2,2,0,0,0-2,2V7a14,14,0,0,0-7.2,2.9,12,12,0,0,1,2.1,3.4A9.1,9.1,0,0,1,34,11.1V13a2,2,0,0,0,2,2h8a2,2,0,0,0,2-2V5A2,2,0,0,0,44,3Zm-2,8H38V7h4Z"/>
<path d="M19.1,34.6A8.6,8.6,0,0,1,14,36.9V35a2,2,0,0,0-2-2H4a2,2,0,0,0-2,2v8a2,2,0,0,0,2,2h8a2,2,0,0,0,2-2V41a13.4,13.4,0,0,0,7.3-3.1A14.6,14.6,0,0,1,19.1,34.6ZM10,41H6V37h4Z"/>
'''),
    "configurations": ("0 0 32 32", '''
<path d="M24,19.171c-1.165,0.412 -2,1.524 -2,2.829c-0,1.305 0.835,2.417 2,2.829l-0,2.171c0,0.552 0.448,1 1,1c0.552,-0 1,-0.448 1,-1l-0,-2.171c1.165,-0.412 2,-1.524 2,-2.829c-0,-1.305 -0.835,-2.417 -2,-2.829l-0,-14.183c0,-0.552 -0.448,-1 -1,-1c-0.552,-0 -1,0.448 -1,1l-0,14.183Zm1,1.829c0.552,0 1,0.448 1,1c-0,0.552 -0.448,1 -1,1c-0.552,0 -1,-0.448 -1,-1c-0,-0.552 0.448,-1 1,-1Z"/>
<path d="M15.006,7.159c-1.164,0.412 -2,1.523 -2,2.829c0,1.305 0.836,2.417 2,2.829l0,14.183c0,0.552 0.448,1 1,1c0.552,0 1,-0.448 1,-1l0,-14.183c1.165,-0.412 2,-1.524 2,-2.829c0,-1.306 -0.835,-2.417 -2,-2.829l0,-2.171c0,-0.552 -0.448,-1 -1,-1c-0.552,-0 -1,0.448 -1,1l0,2.171Zm1,3.829c-0.552,-0 -1,-0.448 -1,-1c0,-0.552 0.448,-1 1,-1c0.552,-0 1,0.448 1,1c0,0.552 -0.448,1 -1,1Z"/>
<path d="M6,19.176c-1.157,0.416 -1.986,1.524 -1.986,2.824c-0,1.3 0.829,2.408 1.986,2.824l0,2.176c-0,0.552 0.448,1 1,1c0.552,0 1,-0.448 1,-1l0,-2.166c1.172,-0.408 2.014,-1.524 2.014,-2.834c-0,-1.31 -0.842,-2.426 -2.014,-2.834l0,-14.178c-0,-0.552 -0.448,-1 -1,-1c-0.552,-0 -1,0.448 -1,1l0,14.188Zm1.014,3.824c-0.552,0 -1,-0.448 -1,-1c-0,-0.552 0.448,-1 1,-1c0.552,0 1,0.448 1,1c-0,0.552 -0.448,1 -1,1Z"/>
'''),
    "benchmark": ("0 0 1920 1920", '''
<path d="M833.935 1063.327c28.913 170.315 64.038 348.198 83.464 384.79 27.557 51.84 92.047 71.944 144 44.387 51.84-27.558 71.717-92.273 44.16-144.113-19.426-36.593-146.937-165.46-271.624-285.064Zm-43.821-196.405c61.553 56.923 370.899 344.81 415.285 428.612 56.696 106.842 15.811 239.887-91.144 296.697-32.64 17.28-67.765 25.411-102.325 25.411-78.72 0-154.955-42.353-194.371-116.555-44.386-83.802-109.102-501.346-121.638-584.245-3.501-23.717 8.245-47.21 29.365-58.277 21.346-11.294 47.096-8.02 64.828 8.357ZM960.045 281.99c529.355 0 960 430.757 960 960 0 77.139-8.922 153.148-26.654 225.882l-10.39 43.144h-524.386v-112.942h434.258c9.487-50.71 14.231-103.115 14.231-156.084 0-467.125-380.047-847.06-847.059-847.06-467.125 0-847.059 379.935-847.059 847.06 0 52.97 4.744 105.374 14.118 156.084h487.454v112.942H36.977l-10.39-43.144C8.966 1395.137.044 1319.128.044 1241.99c0-529.243 430.645-960 960-960Zm542.547 390.686 79.85 79.85-112.716 112.715-79.85-79.85 112.716-112.715Zm-1085.184 0L530.123 785.39l-79.85 79.85L337.56 752.524l79.849-79.85Zm599.063-201.363v159.473H903.529V471.312h112.942Z" fill-rule="evenodd"/>
'''),
}


def script_json(value, **options):
    """JSON for a <script>: '<' is escaped, so a '</script>' in a label cannot end the script."""
    return json.dumps(value, **options).replace("<", "\\u003c")


def icon(name, class_name=""):
    css = f" icon-{class_name}" if class_name else ""
    if name == "brand":
        return (f'<svg class="icon{css}" viewBox="0 0 1920 1920" '
                f'fill="currentColor" aria-hidden="true">{BRAND_ICON_PATHS}</svg>')
    if name in SUMMARY_ICON_SHAPES:
        view_box, paths = SUMMARY_ICON_SHAPES[name]
        return (f'<svg class="icon{css}" viewBox="{view_box}" fill="currentColor" '
                f'aria-hidden="true">{paths}</svg>')
    return (f'<svg class="icon{css}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{ICON_SHAPES[name]}</svg>')


def favicon_svg():
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1920" '
            f'fill="{FAVICON_COLOR}">{BRAND_ICON_PATHS}</svg>')

METRICS = {
    "score": ("Weighted score", True, ".1f"),
    "minutes": ("Work time per run (min)", False, ".1f"),
    "cost": ("Cost per run (USD)", False, ".4f"),
}
# Detail bar charts: the cell field counting instances with data, panel name, anchor and the
# noun used in the missing-value note (English, Chinese).
DETAIL_METRICS = {
    "minutes": {"count": "timeCount", "name": "time", "anchor": "review-minutes",
                "what": ("work time", "耗时")},
    "tokens": {"count": "tokenCount", "name": "token", "anchor": "review-tokens",
               "what": ("token counts", "token 数")},
    "cost": {"count": "costCount", "name": "cost", "anchor": "review-cost",
             "what": ("cost", "费用")},
    "speed": {"count": None, "name": "speed", "anchor": "review-speed",
              "what": ("speed", "速度")},
}
METRIC_LABELS_ZH = {"score": "综合分数", "minutes": "单次运行耗时 (min)",
                    "tokens": "Token 数", "cost": "单次运行费用 (USD)"}
SPEED_LABELS = {
    "taskOutput": ("Task output speed (tok/s)", "任务输出速度 (tok/s)"),
    "taskInput": ("Task input speed (tok/s)", "任务输入速度 (tok/s)"),
    "engineOutput": ("Engine output speed (tok/s)", "引擎输出速度 (tok/s)"),
    "engineInput": ("Engine input speed (tok/s)", "引擎输入速度 (tok/s)"),
}


def series_label(harness, model):
    return f"{MODEL_NAMES[model]} · {HARNESS_NAMES[harness]}"


def series_html(harness, model):
    return f'{MODEL_NAMES[model]} <span style="color:{HARNESS_COLOR}">· {HARNESS_NAMES[harness]}</span>'


def axis_label(record, effort=True):
    """Two-line model name, then effort, then the harness in a quiet gray."""
    lines = MODEL_NAMES[record["model"]].replace(" ", "<br>", 1)
    if effort:
        lines += f'<br>{record["effort"]}'
    return (f'<span style="color:{MODEL_COLORS[record["model"]]}">{lines}</span><br>'
            f'<span style="color:{HARNESS_COLOR}">{HARNESS_NAMES[record["harness"]]}</span>')


def short_value(record, key):
    if key == "cost":
        return f"{'≥' if record['costLowerBound'] else ''}${record[key]:.4f}"
    if key == "minutes":
        return f"{record[key]:.1f} min"
    return f"{record[key]:.1f}"


PLAN_BASIS = ("Price converted to plan subscription fee", "换算成套餐订阅费的价格")
COST_BASIS = {
    "openai": PLAN_BASIS, "google": PLAN_BASIS, "anthropic": PLAN_BASIS,
    "deepseek": ("DeepSeek price per request", "DeepSeek 逐请求价格"),
    "opencode": PLAN_BASIS,
    "strata": ("Local running cost", "本地运行成本"),
}


def hover_summary(record, xkey, ykey):
    """Tooltip source of a scatter point: label, the two values, and for a cost chart one line naming the
    basis of the cost shown (label and value in English, then in Chinese, tab-separated; the tooltip picks the page language)."""
    summary = f"{record['label']}\n{short_value(record, xkey)}\n{short_value(record, ykey)}"
    if "cost" in (xkey, ykey):
        english, chinese = COST_BASIS[record["vendor"]]
        summary += f"\nCost\t{english}\t费用\t{chinese}"
    return summary


def rgba(color, alpha):
    red, green, blue = (int(color[offset:offset + 2], 16) for offset in (1, 3, 5))
    return f"rgba({red},{green},{blue},{alpha})"

def pareto(points, xkey, ykey):
    maximize_x = METRICS[xkey][1]
    maximize_y = METRICS[ykey][1]
    result = []
    for point in points:
        x, y = point[xkey], point[ykey]
        if any((other is not point and
                (other[xkey] >= x if maximize_x else other[xkey] <= x) and
                (other[ykey] >= y if maximize_y else other[ykey] <= y) and
                (other[xkey] != x or other[ykey] != y)) for other in points):
            continue
        result.append(point)
    return sorted(result, key=lambda point: point[xkey])


def chart(records, xkey, ykey, chart_id):
    usable = [record for record in records if record[xkey] is not None and record[ykey] is not None]
    front = pareto(usable, xkey, ykey)
    figure = go.Figure()
    series = sorted({record["series"] for record in usable})
    names = []
    for index, number in enumerate(series):
        points = [record for record in usable if record["series"] == number]
        harness, model = points[0]["harness"], points[0]["model"]
        symbol = HARNESS_SYMBOLS[harness]
        names.append(series_label(harness, model))
        figure.add_trace(go.Scatter(x=[r[xkey] for r in points], y=[r[ykey] for r in points],
                                    mode="lines+markers", showlegend=False, legendgroup=f"model-{index}",
                                    customdata=[hover_summary(r, xkey, ykey) for r in points],
                                    hoverinfo="none",
                                    line={"color": rgba(MODEL_COLORS[model], 0.55), "width": 3},
                                    marker={"size": 11, "symbol": symbol,
                                            "color": MODEL_COLORS[model],
                                            "line": {"color": "#fff", "width": 1.5}}))
    # Static legend traces keep their symbols unchanged when real traces are dimmed or outlined.
    for index, number in enumerate(series):
        point = next(record for record in usable if record["series"] == number)
        symbol = HARNESS_SYMBOLS[point["harness"]]
        color = MODEL_COLORS[point["model"]]
        figure.add_trace(go.Scatter(x=[None], y=[None], mode="lines+markers",
                                    name=series_html(point["harness"], point["model"]) + LEGEND_GAP,
                                    showlegend=True, legendgroup=f"model-{index}", legendrank=index + 1,
                                    hoverinfo="skip",
                                    line={"color": rgba(color, 0.55), "width": 3},
                                    marker={"size": 11, "symbol": symbol, "color": color,
                                            "line": {"color": "#fff", "width": 1.5}}))
    front_x = [r[xkey] for r in front]
    front_y = [r[ykey] for r in front]
    figure.add_trace(go.Scatter(x=front_x, y=front_y, name="Pareto Front" + LEGEND_GAP, mode="lines",
                                visible="legendonly", hoverinfo="skip", legendrank=0,
                                line={"color": PARETO_COLOR, "width": 4}))
    figure.add_trace(go.Scatter(x=front_x, y=front_y, mode="markers", showlegend=False,
                                visible="legendonly", hoverinfo="skip",
                                marker={"size": 11, "color": "rgba(0,0,0,0)",
                                        "line": {"color": PARETO_COLOR, "width": 2.5}}))
    base_layout(figure, height=600, autosize=True,
                margin={"l": 75, "r": 32, "t": 60, "b": 70},
                legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0,
                        "font": {"size": 11}, "groupclick": "togglegroup",
                        # Fixed slots: measured widths overlap for long model · harness names.
                        "entrywidth": 200, "entrywidthmode": "pixels"},
                xaxis_title=METRICS[xkey][0], yaxis_title=METRICS[ykey][0],
                hovermode="closest")
    for axis in (figure.update_xaxes, figure.update_yaxes):
        axis(gridcolor=CHART_GRID, zerolinecolor="#c7bbaa",
             tickfont={"family": CHART_FONT, "size": 11})
    for key, axis in ((xkey, figure.update_xaxes), (ykey, figure.update_yaxes)):
        if key == "cost":
            axis(type="log", dtick="D1", tickprefix="$", showtickprefix="all", tickformat=".3~g")
        elif key == "minutes":
            axis(ticksuffix=" min", showticksuffix="all", tickformat=".0f")
    # Plotly draws later traces on top. Keep the Pareto line after model traces.
    # Recompute the visible 2D frontier whenever a model is hidden or restored in the legend.
    script = """
    const gd = document.getElementById('{plot_id}');
    const frame = document.getElementById('benchmark-frame-CHART_ID');
    const tip = document.getElementById('benchmark-tooltip-CHART_ID');
    // Keep the toolbar above the rendered legend and preserve the plotting height as it wraps.
    const plotHeight = gd.layout.height - gd.layout.margin.t - gd.layout.margin.b;
    // Match the original single-row spacing and the toolbar's -5px inset.
    const toolbarGap = 0.65, toolbarPadding = -5;
    let headerPending = false;
    const fitChartHeader = () => {
      const legend = gd.querySelector('g.legend');
      const toolbar = gd.querySelector('.modebar');
      if (!legend || !toolbar) return;
      const legendBox = legend.getBoundingClientRect();
      const toolbarBox = toolbar.getBoundingClientRect();
      const legendGap = plotHeight * (gd.layout.legend.y - 1);
      const top = Math.round(
        legendBox.height + toolbarBox.height + toolbarGap + toolbarPadding + legendGap);
      const height = plotHeight + top + gd.layout.margin.b;
      // Plotly's HTML wrapper reserves the page's flow height separately from the SVG.
      gd.parentElement.style.height = height + 'px';
      if (gd.layout.margin.t !== top || gd._fullLayout.height !== height) {
        Plotly.relayout(gd, {'margin.t': top, height, autosize: true});
        return;
      }
      const parentBox = toolbar.offsetParent.getBoundingClientRect();
      gd.style.setProperty('--modebar-top',
        (legendBox.top - parentBox.top - toolbarBox.height - toolbarGap) + 'px');
    };
    const scheduleChartHeader = () => {
      if (headerPending) return;
      headerPending = true;
      requestAnimationFrame(() => { headerPending = false; fitChartHeader(); });
    };
    gd.on('plotly_afterplot', scheduleChartHeader);
    scheduleChartHeader();
    frame.addEventListener('wheel', event => {
      if (!event.ctrlKey) event.stopPropagation();
    }, {capture:true, passive:true});
    const modelCount = MODEL_COUNT;
    const frontIndex = modelCount * 2;
    const frontPointsIndex = frontIndex + 1;
    const maximizeX = MAX_X, maximizeY = MAX_Y;
    const modelNames = SERIES_NAMES;
    let hoveredModel = -1;
    let updating = false;
    const focusStyle = document.createElement('style');
    focusStyle.textContent = Array.from({length:modelCount}, (_, index) => {
      const selector = '#' + gd.id + ' .scatterlayer .trace' + gd._fullData[index].uid;
      return `${selector} .js-line {stroke-opacity:var(--model-${index}-line-opacity,.55)!important;stroke-width:var(--model-${index}-line-width,3px)!important}`
        + `${selector} .point {opacity:var(--model-${index}-point-opacity,1)!important}`;
    }).join(' ');
    document.head.appendChild(focusStyle);
    const legendModel = target => {
      const group = target?.closest?.('.legend .traces');
      if (!group || !gd.contains(group)) return -1;
      return modelNames.indexOf(group.querySelector('.legendtext')?.textContent?.trim());
    };
    const applyLegendFocus = () => {
      const focused = hoveredModel >= 0 && gd.data[hoveredModel].visible !== false
        && gd.data[hoveredModel].visible !== 'legendonly' ? hoveredModel : -1;
      for (let index = 0; index < modelCount; index++) {
        gd.style.setProperty(`--model-${index}-line-opacity`,
          String(focused < 0 ? .55 : index === focused ? .8 : .25));
        gd.style.setProperty(`--model-${index}-line-width`, focused === index ? '3.4px' : '3px');
        gd.style.setProperty(`--model-${index}-point-opacity`,
          String(focused < 0 || index === focused ? 1 : .42));
      }
    };
    gd.addEventListener('mouseover', event => {
      const index = legendModel(event.target);
      if (index >= 0 && index !== hoveredModel) {
        hoveredModel = index;
        applyLegendFocus();
      }
    });
    gd.addEventListener('mouseout', event => {
      const from = legendModel(event.target), to = legendModel(event.relatedTarget);
      if (from >= 0 && from !== to && from === hoveredModel) {
        hoveredModel = to;
        applyLegendFocus();
      }
    });
    gd.on('plotly_hover', event => {
      const {points} = event;
      const point = points.find(p => p.curveNumber < modelCount);
      if (!point) return;
      const [label, firstValue, secondValue, ...notes] = point.data.customdata[point.pointNumber]
        .split(String.fromCharCode(10));
      const title = document.createElement('div');
      title.className = 'point-tip-title';
      setTipTitle(title, label);
      const data = document.createElement('div');
      data.className = 'point-tip-values';
      const metrics = document.createElement('div');
      metrics.className = 'point-tip-metrics';
      for (const value of [firstValue, secondValue]) {
        const cell = document.createElement('span');
        cell.className = 'point-tip-metric';
        cell.textContent = value;
        metrics.appendChild(cell);
      }
      data.appendChild(metrics);
      const shift = window.chartLanguage === 'zh' ? 2 : 0;
      const rows = notes.map(line => line.split(String.fromCharCode(9)).slice(shift, shift + 2));
      if (rows.length) {
        const list = document.createElement('div');
        list.className = 'point-tip-rows';
        for (const [name, value] of rows) {
          const row = document.createElement('div');
          row.className = 'point-tip-row';
          for (const [className, text] of [['point-tip-name', name], ['point-tip-value', value]]) {
            const cell = document.createElement('span');
            cell.className = className;
            cell.textContent = text;
            row.appendChild(cell);
          }
          list.appendChild(row);
        }
        data.appendChild(list);
      }
      tip.replaceChildren(title, data);
      tip.style.width = '';
      tip.hidden = false;
      const textWidth = element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return range.getBoundingClientRect().width;
      };
      const cellWidth = Math.max(...[...metrics.children].map(textWidth)) + 9;
      const rowWidth = Math.max(0, ...[...data.querySelectorAll('.point-tip-row')]
        .map(row => [...row.children].reduce((sum, cell) => sum + textWidth(cell), 12)));
      tip.style.width = Math.ceil(Math.max(textWidth(title), cellWidth * 2, rowWidth) + 20) + 'px';
      const frameBox = frame.getBoundingClientRect(), graphBox = gd.getBoundingClientRect();
      const px = Number.isFinite(point.xPixel) ? point.xPixel : event.xPixel;
      const py = Number.isFinite(point.yPixel) ? point.yPixel : event.yPixel;
      const x = graphBox.left - frameBox.left + px;
      const y = graphBox.top - frameBox.top + py - 9;
      tip.style.left = Math.max(tip.offsetWidth / 2 + 6,
        Math.min(frame.clientWidth - tip.offsetWidth / 2 - 6, x)) + 'px';
      tip.style.top = Math.round(Math.max(tip.offsetHeight + 6, y)) + 'px';
    });
    gd.on('plotly_unhover', () => { tip.hidden = true; });
    gd.on('plotly_relayout', () => { tip.hidden = true; });
    gd.on('plotly_restyle', function([changes, indices]) {
      if (updating || !indices.some(i => i <= frontIndex)) return;
      const shown = gd.data[frontIndex].visible !== false && gd.data[frontIndex].visible !== 'legendonly';
      const modelTraces = gd.data.slice(0, modelCount);
      const pts = modelTraces.filter(t => t.visible !== false && t.visible !== 'legendonly')
        .flatMap(t => t.x.map((x, i) => [x, t.y[i]]));
      const front = pts.filter(([x,y]) => !pts.some(([a,b]) =>
        (maximizeX ? a >= x : a <= x) && (maximizeY ? b >= y : b <= y) && (a !== x || b !== y)))
        .sort((a,b) => a[0]-b[0]);
      updating = true;
      const frontX = front.map(p => p[0]), frontY = front.map(p => p[1]);
      Plotly.restyle(gd, {x:[frontX,frontX], y:[frontY,frontY],
                        visible:[shown ? true : 'legendonly', shown ? true : 'legendonly']},
                    [frontIndex,frontPointsIndex])
        .finally(() => { updating = false; applyLegendFocus(); });
    });
    applyLegendFocus();
    """.replace("MAX_X", str(METRICS[xkey][1]).lower()).replace("MAX_Y", str(METRICS[ykey][1]).lower())
    script = script.replace("MODEL_COUNT", str(len(series))).replace("CHART_ID", str(chart_id))
    script = script.replace("SERIES_NAMES", script_json(names))
    # plotly.js itself is embedded once, by effort_score_chart.
    return pio.to_html(figure, full_html=False, include_plotlyjs=False,
                       post_script=script, div_id=f"benchmark-scatter-{chart_id}",
                       config={"responsive": True, "displaylogo": False, "scrollZoom": True})


def cell_rows(cell, language):
    en = language == "en"
    rows = [("Mean ± 95% CI" if en else "均值 ± 95% 区间",
             f"{100 * cell['mean']:.1f} ± {100 * cell['half']:.1f}" if cell["half"] is not None
             else f"{100 * cell['mean']:.1f}"),
            ("Instances" if en else "实例数", str(cell["n"])),
            ("SD" if en else "标准差", f"{100 * cell['sd']:.1f}" if cell["sd"] is not None else "—"),
            ("Min / median" if en else "最小 / 中位数",
             f"{100 * cell['min']:.1f} / {100 * cell['median']:.1f}")]
    if cell["negatives"]:
        rows.append(("Negative scores" if en else "负分实例", str(cell["negatives"])))
    if cell["failures"]:
        rows.append(("Model failures (0)" if en else "模型失误 (记 0)", str(cell["failures"])))
    return rows


def scenario_details(record, key, name, language):
    cell = record["cells"][key]
    return {"label": record["label"], "meta": name,
            "rows": [{"name": label, "color": CHART_TEXT, "display": value}
                     for label, value in cell_rows(cell, language)]}


def bar_tooltip_script(chart_id, details_en, details_zh, by_role=False):
    script = """
    const gd = document.getElementById('{plot_id}');
    const tip = document.getElementById('benchmark-bar-tooltip-CHART_ID');
    document.body.appendChild(tip);
    const viewport = gd.closest('.bar-viewport');
    const axisOverlay = gd.closest('.bar-frame')?.querySelector('.bar-axis-overlay');
    const keepModebarVisible = () => {
      const modebar = gd.querySelector('.modebar-container');
      if (!modebar) return;
      const overflow = Math.max(0, gd.clientWidth - viewport.clientWidth);
      modebar.style.width = Math.min(gd.clientWidth, viewport.clientWidth) + 'px';
      modebar.style.right = Math.max(0, overflow - viewport.scrollLeft) + 'px';
    };
    const keepLegendVisible = () => {
      if (!axisOverlay) return;
      const legend = gd.querySelector('g.legend');
      if (!legend) return;
      // CSS translate adds to Plotly's SVG transform and survives its legend redraws.
      legend.style.translate = `${viewport.scrollLeft}px 0`;
    };
    const drawFrozenAxis = () => {
      if (!axisOverlay) return;
      const svgs = [...gd.querySelectorAll('svg.main-svg')];
      const tickSvg = svgs.find(svg => svg.querySelector('.yaxislayer-above'));
      const titleSvg = svgs.find(svg => svg.querySelector('.g-ytitle'));
      if (gd.clientWidth <= viewport.clientWidth || !tickSvg) {
        axisOverlay.hidden = true;
        axisOverlay.replaceChildren();
        return;
      }
      const cloneParts = (source, selectors) => {
        const clone = source.cloneNode(true);
        const keepAxis = node => {
          if (node.matches?.(selectors)) return true;
          let kept = false;
          for (const child of [...node.children]) {
            if (keepAxis(child)) kept = true;
            else child.remove();
          }
          return kept;
        };
        keepAxis(clone);
        clone.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
        clone.setAttribute('aria-hidden', 'true');
        return clone;
      };
      const ticks = cloneParts(tickSvg,
        '.yaxislayer-above, .yaxislayer-below, .ylines-above, .g-ytitle');
      const title = titleSvg && titleSvg !== tickSvg
        ? cloneParts(titleSvg, '.g-ytitle') : null;
      const axisWidth = gd._fullLayout?._size?.l ?? gd.layout.margin.l;
      axisOverlay.style.width = Math.ceil(axisWidth) + 2 + 'px';
      axisOverlay.style.height = tickSvg.getBoundingClientRect().height + 'px';
      axisOverlay.replaceChildren(ticks, ...(title ? [title] : []));
      axisOverlay.hidden = false;
      if (typeof fitLogTickLabels === 'function') fitLogTickLabels(gd, 'yaxis', axisOverlay);
    };
    viewport.addEventListener('scroll', () => {
      keepModebarVisible();
      keepLegendVisible();
    }, {passive:true});
    window.addEventListener('resize', () => {
      keepModebarVisible();
      keepLegendVisible();
      drawFrozenAxis();
    });
    new ResizeObserver(() => {
      keepModebarVisible();
      keepLegendVisible();
      drawFrozenAxis();
    }).observe(viewport);
    gd.on('plotly_afterplot', () => requestAnimationFrame(() => {
      keepModebarVisible();
      keepLegendVisible();
      drawFrozenAxis();
    }));
    keepModebarVisible();
    keepLegendVisible();
    drawFrozenAxis();
    const detailsByLanguage = {en: DETAILS_EN, zh: DETAILS_ZH};
    const byRole = BY_ROLE;
    let lastMouse = null;
    const add = (parent, tag, className, content) => {
      const element = document.createElement(tag);
      element.className = className;
      element.textContent = content;
      parent.appendChild(element);
      return element;
    };
    const place = event => {
      let left = event.clientX + 15, top = event.clientY + 15;
      if (left + tip.offsetWidth + 8 > window.innerWidth) left = event.clientX - tip.offsetWidth - 15;
      if (top + tip.offsetHeight + 8 > window.innerHeight) top = event.clientY - tip.offsetHeight - 15;
      tip.style.left = Math.max(8, left) + 'px';
      tip.style.top = Math.max(8, top) + 'px';
    };
    gd.addEventListener('mousemove', event => {
      lastMouse = event;
      if (!tip.hidden) place(event);
    });
    gd.on('plotly_hover', event => {
      const group = detailsByLanguage[window.chartLanguage || 'en'][event.points[0]?.x];
      const detail = byRole ? group?.[event.points[0]?.data?.meta] : group;
      if (!detail) return;
      tip.replaceChildren();
      setTipTitle(add(tip, 'strong', 'bar-tip-title', ''), detail.label);
      add(tip, 'div', 'bar-tip-meta', detail.meta);
      for (const row of detail.rows) {
        const line = add(tip, 'div', 'bar-tip-row', '');
        const dot = add(line, 'span', 'bar-tip-dot', '');
        dot.style.backgroundColor = row.color;
        add(line, 'span', 'bar-tip-name', row.name);
        add(line, 'strong', 'bar-tip-value', row.display ?? row.value.toFixed(row.digits));
      }
      tip.hidden = false;
      if (lastMouse) place(lastMouse);
    });
    gd.on('plotly_unhover', () => { tip.hidden = true; });
    gd.addEventListener('mouseleave', () => { tip.hidden = true; });
    """
    return (script.replace("CHART_ID", chart_id)
            .replace("BY_ROLE", str(by_role).lower())
            .replace("DETAILS_EN", script_json(details_en, ensure_ascii=False))
            .replace("DETAILS_ZH", script_json(details_zh, ensure_ascii=False)))

SCORE_TRACK = "#ebe5da"
SCORE_FLOOR = -20


def effort_bar_color(model, effort):
    base = MODEL_COLORS[model]
    rgb = [int(base[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    hue, _, _ = colorsys.rgb_to_hls(*rgb)
    strength = EFFORTS[effort]
    lightness = 0.30 + strength * 0.11
    saturation = 0.24 + strength * 0.075
    channels = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in channels)


def score_range(pairs):
    """Return a y range showing the full 0-100 track and at most SCORE_FLOOR below 0.

    Deeper negative values would squeeze the positive half; panning reveals them.
    """
    low = min([0.0] + [value - (half or 0) for value, half in pairs])
    return [max(math.floor(low / 10) * 10, SCORE_FLOOR), 112]


def score_bars(figure, x, values, halves, colors, track_text, **position):
    """Add a 0-100 track with the value above it, then the score bar with its 95% CI."""
    figure.add_trace(go.Bar(x=x, y=[100] * len(x), base=0, marker_color=SCORE_TRACK,
                            showlegend=False, hoverinfo="none", text=track_text,
                            textposition="outside", textangle=0, cliponaxis=False,
                            textfont={"color": CHART_TEXT, "family": CHART_FONT, "size": 10},
                            **position))
    figure.add_trace(go.Bar(x=x, y=values, marker_color=colors, hoverinfo="none",
                            error_y={"type": "data", "array": [half or 0 for half in halves],
                                     "visible": True, "color": "#3d3a35", "thickness": 1.2,
                                     "width": 3},
                            **position))


def base_layout(figure, **layout):
    """Shared Plotly look: transparent paper, tinted plot area, chart font, panning."""
    figure.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor=CHART_PLOT, dragmode="pan",
                         font={"color": CHART_TEXT, "family": CHART_FONT}, **layout)


def score_layout(figure, y_range, **layout):
    base_layout(figure, yaxis_title="Score", yaxis_range=y_range, **layout)
    figure.update_yaxes(gridcolor=CHART_GRID, zeroline=True, zerolinecolor="#8f8577",
                        zerolinewidth=1.5, tickfont={"family": CHART_FONT, "size": 11})


def effort_score_chart(records):
    """Weighted score per configuration, one group per model and harness."""
    series = sorted({record["series"] for record in records})
    groups = [sorted((record for record in records if record["series"] == number),
                     key=lambda record: -EFFORTS[record["effort"]]) for number in series]
    bar_width, bar_gap, group_gap = 0.27, 0.02, 0.15
    # Each group is as wide as its bars, so a model with more effort levels takes more room.
    widths = [len(group) * bar_width + (len(group) - 1) * bar_gap for group in groups]
    centers, cursor = [], -widths[0] / 2
    for width in widths:
        center = round(cursor + width / 2, 3)
        # Whole centers as int, so the tooltip keys match the x values JavaScript reports.
        centers.append(int(center) if center == int(center) else center)
        cursor += width + group_gap
    details = {language: {} for language in ("en", "zh")}
    for position, group in zip(centers, groups):
        title = series_label(group[0]["harness"], group[0]["model"])
        for language in details:
            rows = [{"name": record["effort"], "color": effort_bar_color(record["model"], record["effort"]),
                     "display": f"{record['score']:.1f}"
                                + (f" ± {record['half']:.1f}" if record["half"] is not None else "")}
                    for record in group]
            meta = "Weighted score ± 95% CI" if language == "en" else "综合分数 ± 95% 区间"
            details[language][position] = {"label": title, "meta": meta, "rows": rows}
    figure = go.Figure()
    for effort in sorted(EFFORTS, key=EFFORTS.get, reverse=True):
        x, values, halves, offsets, colors = [], [], [], [], []
        for position, group, group_width in zip(centers, groups, widths):
            efforts = [record["effort"] for record in group]
            if effort not in efforts:
                continue
            record = group[efforts.index(effort)]
            x.append(position)
            values.append(record["score"])
            halves.append(record["half"])
            offsets.append(-group_width / 2 + efforts.index(effort) * (bar_width + bar_gap))
            colors.append(effort_bar_color(record["model"], effort))
        score_bars(figure, x, values, halves, colors, [f"{value:.1f}" for value in values],
                   offset=offsets, width=bar_width)
    score_layout(figure, score_range([(record["score"], record["half"]) for record in records]),
                 barmode="overlay", showlegend=False, height=540, autosize=True,
                 margin={"l": 65, "r": 25, "t": 36, "b": 78})
    labels = [axis_label(group[0], effort=False) for group in groups]
    edge = group_gap / 2 + 0.1
    figure.update_xaxes(tickmode="array", tickvals=centers, ticktext=labels,
                        range=[centers[0] - widths[0] / 2 - edge, centers[-1] + widths[-1] / 2 + edge],
                        tickangle=0, tickfont={"size": 11})
    return pio.to_html(figure, full_html=False, include_plotlyjs=True, div_id="benchmark-bars-effort",
                       post_script=bar_tooltip_script("effort", details["en"], details["zh"]),
                       config={"responsive": True, "displaylogo": False,
                               "displayModeBar": "hover", "doubleClick": "reset"})


def task_score_chart(records):
    """Each configuration's four task scores with their 95% intervals."""
    xlabels = [record["label"] for record in records]
    details = {language: {record["label"]: [scenario_details(record, key, name, language)
                                            for key, name, _ in REVIEWERS]
                          for record in records} for language in ("en", "zh")}
    figure = go.Figure()
    pairs = []
    for index, (key, name, _) in enumerate(REVIEWERS):
        cells = [record["cells"][key] for record in records]
        values = [100 * cell["mean"] for cell in cells]
        halves = [100 * cell["half"] if cell["half"] is not None else None for cell in cells]
        pairs += zip(values, halves)
        score_bars(figure, xlabels, values, halves, ROLE_COLORS[index],
                   [f"{value:.0f}" for value in values], offsetgroup=str(index), meta=index)
        figure.data[-1].update(name=name + LEGEND_GAP)
    score_layout(figure, score_range(pairs), barmode="group", bargap=0.18, bargroupgap=0.10,
                 height=600, width=max(1200, len(xlabels) * 84),
                 margin={"l": 65, "r": 25, "t": 95, "b": 110},
                 legend={"orientation": "h", "y": 1.02, "yanchor": "bottom"})
    figure.update_xaxes(categoryorder="array", categoryarray=xlabels,
                        tickmode="array", tickvals=xlabels,
                        ticktext=[axis_label(record) for record in records],
                        tickangle=0, tickfont={"size": 11})
    return pio.to_html(figure, full_html=False, include_plotlyjs=False, div_id="benchmark-bars-grouped",
                       post_script=bar_tooltip_script("grouped", details["en"], details["zh"],
                                                      by_role=True),
                       config={"responsive": True, "displaylogo": False,
                               "displayModeBar": "hover", "doubleClick": "reset"})


def detail_values(cell, metric, speed=None):
    if metric == "tokens":
        return cell["tokens"]
    if metric == "speed":
        return cell["speeds"][speed]
    return cell[metric]


def detail_meta(cell, metric, name, language, speed=None):
    en = language == "en"
    if metric == "speed":
        used = cell["speedCounts"][speed]
    else:
        used = cell[DETAIL_METRICS[metric]["count"]]
    text = (f"{name}\n{used}/{cell['n']} instances with data" if en
            else f"{name}\n{used}/{cell['n']} 个实例有数据")
    # Cost and speed values carry their own ≥; token counts are shown plain, so the meta line marks them.
    if metric == "tokens" and cell["tokenLowerBound"]:
        text += "\nLower bounds (≥)" if en else "\n含下限值 (≥)"
    return text


def detail_bar_chart(records, metric):
    xlabels = [record["label"] for record in records]
    ticktext = [axis_label(record) for record in records]
    kinds = SPEED_KEYS if metric == "speed" else (None,)
    details = {language: {} for language in ("en", "zh")}
    for record in records:
        for language in details:
            role_details = []
            for speed in kinds:
                for index, (key, name, _) in enumerate(REVIEWERS):
                    cell = record["cells"][key]
                    value = detail_values(cell, metric, speed)
                    if value is None:
                        role_details.append(None)
                        continue
                    meta = detail_meta(cell, metric, name, language, speed)
                    if metric == "tokens":
                        names = (("uncachedInput", "Non-cached input", "未缓存输入"),
                                 ("cachedInput", "Cached input", "缓存输入"),
                                 ("output", "Output", "输出"))
                        rows = [{"name": english if language == "en" else chinese,
                                 "color": TOKEN_COLORS[token], "display": f"{value[token]:,.0f}"}
                                for token, english, chinese in names]
                        rows.append({"name": "Total" if language == "en" else "合计",
                                     "color": CHART_TEXT, "display": f"{sum(value.values()):,.0f}"})
                    else:
                        if metric == "minutes":
                            display, row_name = f"{value:.1f} min", ("Work time", "耗时")
                        elif metric == "cost":
                            display = f"{'≥' if cell['costLowerBound'] else ''}${value:.4f}"
                            row_name = COST_BASIS[record["vendor"]]
                        else:
                            bound = "≥" if cell["speedLowerBounds"][speed] else ""
                            display, row_name = f"{bound}{value:,.1f} tok/s", SPEED_LABELS[speed]
                        rows = [{"name": row_name[0] if language == "en" else row_name[1],
                                 "color": ROLE_COLORS[index], "display": display}]
                    role_details.append({"label": record["label"], "meta": meta, "rows": rows})
            details[language][record["label"]] = role_details
    figure = go.Figure()
    if metric == "tokens":
        for token, english in (("uncachedInput", "Non-cached input"),
                               ("cachedInput", "Cached input"), ("output", "Output")):
            for index, (key, _, _) in enumerate(REVIEWERS):
                values = [record["cells"][key]["tokens"] for record in records]
                figure.add_trace(go.Bar(
                    x=xlabels, y=[usage[token] if usage is not None else None for usage in values],
                    name=english + LEGEND_GAP, marker_color=TOKEN_COLORS[token],
                    offsetgroup=str(index), legendgroup=token, showlegend=index == 0,
                    legendrank=TOKEN_KEYS.index(token) + 1, meta=index, hoverinfo="none"))
    else:
        for kind_index, speed in enumerate(kinds):
            for index, (key, name, _) in enumerate(REVIEWERS):
                values = [detail_values(record["cells"][key], metric, speed) for record in records]
                figure.add_trace(go.Bar(x=xlabels, y=values, name=name + LEGEND_GAP,
                                        marker_color=ROLE_COLORS[index],
                                        meta=kind_index * len(REVIEWERS) + index,
                                        visible=kind_index == 0, hoverinfo="none"))
    title = {"minutes": METRICS["minutes"][0], "tokens": "Tokens per run",
             "cost": METRICS["cost"][0], "speed": SPEED_LABELS[SPEED_KEYS[0]][0]}[metric]
    base_layout(figure, barmode="stack" if metric == "tokens" else "group", bargap=0.18,
                bargroupgap=0.10, height=600, width=max(1200, len(xlabels) * 84),
                margin={"l": 75, "r": 25, "t": 95, "b": 110},
                legend={"orientation": "h", "y": 1.02, "yanchor": "bottom"},
                yaxis_title=title)
    figure.update_xaxes(categoryorder="array", categoryarray=xlabels,
                        tickmode="array", tickvals=xlabels, ticktext=ticktext,
                        tickangle=0, tickfont={"size": 11})
    figure.update_yaxes(gridcolor=CHART_GRID, zerolinecolor="#c7bbaa",
                        tickfont={"family": CHART_FONT, "size": 11})
    if metric == "tokens":
        figure.update_yaxes(tickformat="~s")
    elif metric == "cost":
        figure.update_yaxes(type="log", dtick="D1", tickprefix="$", showtickprefix="all", tickformat=".3~g")
    elif metric == "minutes":
        figure.update_yaxes(ticksuffix=" min", showticksuffix="all", tickformat=".0f")
    else:
        figure.update_yaxes(tickformat=",.0f")
    return pio.to_html(figure, full_html=False, include_plotlyjs=False,
                       div_id=f"benchmark-bars-{metric}",
                       post_script=bar_tooltip_script(metric, details["en"], details["zh"],
                                                      by_role=True),
                       config={"responsive": True, "displaylogo": False,
                               "displayModeBar": "hover", "doubleClick": "reset"})


def partial_note(records, metric, language):
    """Describe cells whose mean uses fewer instances than the cell holds."""
    en = language == "en"
    partial = []
    for record in records:
        for key, name, _ in REVIEWERS:
            cell = record["cells"][key]
            if metric == "speed":
                # API models have no engine input speed at all (see README); that is not a gap.
                counts = [(f" · {SPEED_LABELS[speed][0 if en else 1].split(' (')[0]}",
                           cell["speedCounts"][speed]) for speed in SPEED_KEYS
                          if (speed != "engineInput" or record["vendor"] == "strata")
                          and not (record["harness"] == "antigravity" and speed.startswith("engine"))]
            else:
                counts = [("", cell[DETAIL_METRICS[metric]["count"]])]
            for speed_name, count in counts:
                if count < cell["n"]:
                    partial.append(f"{name} · {record['label']}{speed_name} ({count}/{cell['n']})")
    if not partial:
        return ""
    names = "; ".join(partial)
    what = DETAIL_METRICS[metric]["what"]
    return (f"Some instances have no {what[0]}: {names}. Those means use the instances with data."
            if en else
            f"部分实例没有{what[1]}: {names}. 这些均值只用有数据的实例.")


def toggle_group(class_name, group_attrs, label_key, label_en, data_key, options, pressed):
    """A labeled button group; the button whose value equals `pressed` starts pressed."""
    buttons = "".join(
        f'<button type="button" data-{data_key}="{value}" data-i18n="{i18n_key}" '
        f'aria-pressed="{str(value == pressed).lower()}">{text}</button>'
        for value, i18n_key, text in options)
    return (f'<div class="{class_name}" {group_attrs}>'
            f'<span data-i18n="{label_key}">{label_en}</span>{buttons}</div>')


def segment_control(control_id, options, data_key, i18n_label, label_en):
    return toggle_group("segment-control", f'id="{control_id}" role="group"', i18n_label, label_en,
                        data_key, options, options[0][0])


def cost_scale_control(plot_id, axis, default_scale="log"):
    return toggle_group("cost-scale-control",
                        f'role="group" data-plot="{plot_id}" data-axis="{axis}" '
                        'aria-label="Cost axis scale"',
                        "cost_scale", "Cost scale", "scale",
                        (("linear", "scale_linear", "Linear"), ("log", "scale_log", "Log")),
                        default_scale)


def usd(value):
    """Format a price: whole dollars bare, otherwise two decimals, or more when needed."""
    if value == int(value):
        return f"${int(value)}"
    return f"${value:.2f}" if round(value, 2) == value else f"${value:g}"


def join_and(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def cost_method_values(pricing):
    """Prices, power and electricity rate for the cost method text, read from pricing.json."""
    if pricing["tokensPerUnit"] != 1_000_000:
        raise ValueError("The method text says per million tokens; update it for a new unit.")
    rates = [(MODEL_NAMES[model], " / ".join(usd(rule["rates"][key]) for key in TOKEN_KEYS))
             for model, rule in pricing["openai"].items()]
    google = [(MODEL_NAMES[model], " / ".join(usd(rule["rates"][key]) for key in TOKEN_KEYS))
              for model, rule in pricing["google"].items()]
    local = pricing["localRunningCost"]["strata-iq3_xxs"]
    if "planCost" in pricing:  # v2: the page text comes from v2_overrides; these v1 figures do not exist
        plan_values = {key: "" for key in ("point_usd", "week_usd", "week_api", "week_points", "week_checked",
                                           "e_claude", "e_gpt", "e_gemini", "plan_checked")}
    else:
        points = pricing["taskPoints"]
        e = {vendor: f"{rule['e']:.3g}" for vendor, rule in points["efficiency"].items()}
        plan = points["plan"]
        plan_values = {"point_usd": usd(points["pointUsd"]), "week_usd": usd(round(plan_weekly_cost(pricing), 2)),
                       "week_api": usd(plan["weeklyPoints"] * points["pointUsd"]),
                       "week_points": f"{plan['weeklyPoints']:g}", "week_checked": plan["weeklyPointsCheckedAt"],
                       "e_claude": e["anthropic"], "e_gpt": e["openai"], "e_gemini": e["google"],
                       "plan_checked": points["checkedAt"]}
    return {**plan_values,
            "rates": rates, "google_rates": google,
            "watts": f"{local['wallPowerWatts']:g}",
            "electricity": usd(local["electricityUsdPerKwh"]),
            "upkeep": usd(local["maintenanceUsdPerHour"]), "checked": pricing["checkedAt"]}


def run_count_method_values(records):
    """Describe scored cell sizes from the same records used by the charts."""
    counts = Counter(cell["n"] for record in records for cell in record["cells"].values())
    low, high = min(counts), max(counts)
    return {
        "en_range": str(low) if low == high else f"{low} to {high}",
        "zh_range": str(low) if low == high else f"{low} 至 {high}",
        "en_counts": "; ".join(f"{cells} {'cell' if cells == 1 else 'cells'} with {n} runs"
                               for n, cells in sorted(counts.items())),
        "zh_counts": "; ".join(f"{cells} 格各 {n} 次" for n, cells in sorted(counts.items())),
    }


def page_copy(pricing, records):
    weights = " + ".join(f"{weight:.2f} {name}" for _, name, weight in REVIEWERS)
    cost = cost_method_values(pricing)
    runs = run_count_method_values(records)
    rates_en = join_and([f"{name} {rate}" for name, rate in cost["rates"]])
    rates_zh = ", ".join(
        f"{name} 每百万未缓存输入、缓存输入、输出 token 为 {rate}" if index == 0 else f"{name} 为 {rate}"
        for index, (name, rate) in enumerate(cost["rates"]))
    google_en = join_and([f"{name} {rate}" for name, rate in cost["google_rates"]])
    google_zh = ", ".join(f"{name} 为 {rate}" for name, rate in cost["google_rates"])
    return {
        "en": {
            "brand": "Reviewer Model\nBenchmark",
            "topbar_context": "Model performance overview", "nav_label": "EXPLORE",
            "nav_overview": "Overview", "nav_score": "Weighted score",
            "nav_tradeoffs": "Trade-offs", "nav_cost_score": "Cost vs. score",
            "nav_time_score": "Time vs. score", "nav_time_cost": "Time vs. cost",
            "nav_reviewers": "Task breakdown",
            "nav_reviewer_score": "Scores", "nav_reviewer_time": "Work time",
            "nav_reviewer_tokens": "Token usage", "nav_reviewer_cost": "Cost",
            "nav_reviewer_speed": "Speed",
            "nav_method": "Method & data",
            "eyebrow": "MODEL COMPARISON / BENCHMARK",
            "headline": "Comparing AI models for software review",
            "lead": "A Reviewer is an AI agent assigned a software review task. Here, {model_count} models run four such tasks through two agent harnesses, Codex and Claude Code, at different reasoning effort settings; the charts compare their task performance, time and cost.",
            "version_title": f"Benchmark v{PAGE_VERSION}",
            "version_summary": f"Adds GPT-6 Luna at xhigh and max effort (a supplement run one day later) and Gemini 4 Hydrogen at low, medium, high and xhigh effort (a supplement run about three weeks later, in the Antigravity harness; low was run a day after the other three) to the v2.0 run (new models, two harnesses, scoring {SCORING_VERSION} with scores that can be negative). Each task cell counts {runs['en_range']} scored runs. v2.4 to v2.6 change only the cost basis, not the data: every subscription-plan run (Claude, GPT and Gemini models) is now converted to a subscription price, its share of the Claude $100 plan's weekly fee ({cost['week_usd']}), the share found through equivalent task points (v2.4 had priced only Claude and GPT by their share of a $100 plan's weekly quota; v2.5 showed all plan runs in Claude API dollars; v2.6 returns to the plan fee for all of them, with the same ratios between plan runs as v2.5). DeepSeek and Strata stay in actual-cost dollars. Results are not comparable with v1.",
            "version_readme": "For the measurement rules, see the project",
            "stat_models": "MODELS", "stat_configurations": "CONFIGURATIONS",
            "stat_benchmarks": "REVIEWER TASKS", "stat_runs": "SCORED RUNS",
            "readme_more": "For details, see the project",
            "score_kicker": "01 / QUALITY", "score_title": "Weighted score by reasoning effort",
            "score_desc": "Each model in one harness forms a group. Its bars show reasoning effort levels, ordered from highest to lowest. The light track behind each bar spans the full 0 to 100 scale, so bar height shows absolute ability; the whisker shows the 95% confidence interval.",
            "score_context": "Effort labels are requested settings, not equal compute across models. The tasks were calibrated on Claude Opus, which also judged the reports, so Opus may be placed too high. The benchmark's own report gives per-task results only; the weighted score is this page's summary of them.",
            "score_models": "DeepSeek V4.1 Flash is the endpoint's deepseek-flash model, version DeepSeek-V4.1-Flash-1017. Strata IQ3_XXS is a 3-bit quantization of Qwen3.8-Flash-Next run locally on one RTX 3080 Ti (12 GB).",
            "score_read": "Each group is a model in one harness and each bar an effort setting. The number above a track is the weighted score; taller is better. A score falls below 0 when a report's false findings outweigh its correct ones. This result covers these review tasks, not general model ability.",
            "trade_kicker": "02 / TRADE-OFFS", "trade_title": "Quality, time and cost",
            "trade_intro": "Each point is one configuration. Lines join the effort levels of one model in one harness: circles mark Codex and diamonds Claude Code. A Pareto-front point has no other visible point that is at least as good on both plotted measures and better on one. Click Pareto Front in a legend to show those points and their connecting line. Hold Ctrl while scrolling over a chart to zoom.",
            "cost_score_title": "Cost per run vs. score",
            "cost_score_desc": f"Cost per run averages each task's per-run cost, then the four tasks. The bases differ by vendor and none is an actual bill: for every subscription-plan run (Claude, GPT and Gemini models), the share of the Claude $100 plan's weekly fee ({cost['week_usd']}) that the run used up; for DeepSeek, per-request prices; and for the local Strata model, estimated electricity and upkeep.",
            "cost_score_read": "Higher score is better; farther left is a lower cost per run. Hover a point for its values; ≥ marks a lower bound. The cost shown is one comparable figure: for a subscription-plan run (Claude, GPT, Gemini) its price converted to the plan's subscription fee, for DeepSeek and Strata the actual cost. The conversion follows one rule: a run that uses 1/100 of the $100 plan's weekly quota costs 1/100 of its weekly fee (see Data notes). Use Linear / Log above the chart to switch the cost axis: Linear shows absolute differences; Log helps compare costs across a wide range.",
            "time_score_title": "Work time vs. score",
            "time_score_desc": "Compare the weighted score with the average work time of one review run.",
            "time_score_read": "Higher score is better; farther left is a shorter run. Work time excludes setup and loading. Codex counts the agent's accumulated work time and Claude Code the session's wall time. Code Spec and Code Standards stop at a time limit set from each configuration's own speed and held between 15 and 60 minutes; a run that is stopped by the limit is voided and rerun, so every counted run ended before its limit. Two caveats: runs made before the 15-60 minute rule used their original limits (the voided runs were then rerun at 60 minutes, some on a newer Claude Code version), and the DeepSeek-flash max Code Spec (Claude Code) cell has 4 counted runs instead of 5 because its rerun could not be made.",
            "time_cost_title": "Work time vs. cost per run",
            "time_cost_desc": "Inspect the relationship between run time and cost.",
            "time_cost_read": "Farther left is a shorter run; lower is a lower cost per run. The cost, a price converted to the plan's subscription fee or the actual cost, is explained under Cost per run vs. score. This plot does not encode quality, so use it alongside the score charts. Use Linear / Log above the chart to switch the cost axis.",
            "cost_scale": "Cost scale", "scale_linear": "Linear", "scale_log": "Log",
            "review_kicker": "03 / TASK DETAIL", "review_title": "Results by reviewer task",
            "review_desc": "Compare each configuration's score, work time, token usage, cost and speed in each of the four reviewer tasks.",
            "detail_score_title": "Task scores",
            "detail_time_title": "Work time by task",
            "detail_token_title": "Token usage by task",
            "detail_cost_title": "Cost by task",
            "detail_speed_title": "Speed by task",
            "speed_label": "Speed",
            "speed_task_output": "Task output", "speed_task_input": "Task input",
            "speed_engine_output": "Engine output", "speed_engine_input": "Engine input",
            "detail_score_read": f"Each bar is the mean score of the runs the benchmark counts. Scored runs per cell: {runs['en_counts']}. The number above a track is the mean and the whisker the 95% confidence interval; with about five runs, a difference below about 30 points may be noise. The label color identifies the model. Scroll horizontally to compare all configurations.",
            "detail_time_read": "Each bar is one task's mean work time per run. Spec Readiness runs two independent review threads per run; their times are added.",
            "detail_token_read": "Each bar stacks mean non-cached input, cached input and output tokens per run. Claude Code counts cache writes as non-cached input; Strata on Codex includes its guardian requests. Hover for exact counts.",
            "detail_cost_read": "Each bar is one task's mean cost per run. OpenAI, Claude and Gemini runs used subscriptions, so theirs are priced as a share of the Claude $100 plan's weekly fee (the price converted to the plan's subscription fee; the conversion is explained in the Data notes). DeepSeek and Strata are priced in actual-cost dollars (see Data notes). Use Linear / Log above the chart to switch the cost axis.",
            "detail_speed_read": "A speed is total tokens divided by total seconds, never an average of per-run speeds. Task speeds divide non-cached input or output tokens by work time: the speed a user perceives. Engine speeds measure the model alone. API models cannot separate input processing, so their engine input speed is unknown and their engine output speed is a lower bound (≥); engine input speed exists only for Strata.",
            "reviewer_guide_title": "The four reviewer tasks and their score shares",
            "score_share_label": "Score share",
            "reviewer_standards": "Reviews code changes against repository instructions and implementation quality standards.",
            "reviewer_spec": "Checks whether code changes implement the requirements supplied for the task accurately and completely.",
            "reviewer_audit": "Audits a staged commit candidate: the selected files, required checks and coverage of the supplied requirements.",
            "reviewer_readiness": "Before implementation, checks whether requirement documents are complete, consistent, feasible and verifiable. Each run has two independent review threads.",
            "method_kicker": "DATA NOTES", "method_title": "How scores and costs are calculated",
            "method_selection": f"The data are the benchmark's per-run results. The page uses the runs the benchmark counts in its main statistics. Scored runs per cell: {runs['en_counts']}. GPT-6 Luna xhigh and max are a supplement run a day later with every valid run counted; the benchmark does not compare them with other configurations. Gemini 4 Hydrogen low, medium, high and xhigh are a supplement run about three weeks later (low a day after the other three) in a different harness (Antigravity; its version was 1.5.8 for some runs and 1.5.9 for others), with every valid run counted; the benchmark does not compare them with other configurations either. DeepSeek runs requested as medium count as high where the endpoint ran them as high under the same time limit. Invalid runs and the supplementary DeepSeek configuration requested as medium under a different time limit are excluded. The task suite is a frozen copy of ARW commit 760007c plus patches, scored with r8.4; the snapshots' sources are recorded in sources.json.",
            "method_score": f"A run's score (scoring {SCORING_VERSION}) credits the answer-key problems a report finds and deducts its false findings. It is not cut at 0, so it can be negative, and a run that produced no report scores 0. A task score is the mean of its runs, with a 95% interval from the t distribution. The weighted score is 100 × ({weights}); its interval combines the four standard errors with Welch–Satterthwaite degrees of freedom.",
            "method_runtime": "Time and tokens average every counted run, including zero-score runs, which still used resources. A task's value is the mean over its runs with data; a configuration's value is the arithmetic mean of its four task values. Speeds are total tokens over total seconds, never a mean of speeds: a task's speed pools its runs.",
            "method_cost": f"Cost per run: DeepSeek uses the benchmark's per-request cost at official prices; Claude, GPT and Gemini models ran on subscription plans, and all of them are converted into one subscription price, the Claude $100 plan's weekly fee ({cost['week_usd']}: $100 a month over a 30-day month, times 7 days). A run's cost is the share of that plan's weekly quota it uses, times the weekly fee. For example, if one $100 plan week allowed 10G tokens of a small model but only 1G of a large one, then 100M tokens of each would use 1/100 and 1/10 of the week, so they cost 1/100 and 1/10 of the weekly fee. The share is found through equivalent task points: one point is a fixed amount of Claude API spending ({cost['point_usd']}), a Claude $100 plan week holds {cost['week_points']} points (about {cost['week_api']} of Claude API-priced use, measured on {cost['week_checked']}), and a plan category's efficiency ratio E is what Claude would have spent on the same kind of finished work divided by what that plan spent (from the author's own usage history). A run's points are its API-equivalent cost × E ÷ {cost['point_usd']}, and its cost is points ÷ {cost['week_points']} × {cost['week_usd']}. The API-equivalent cost is, for Claude models, the cost Claude Code reports; for GPT models, token counts at OpenAI Standard API rates ({rates_en} per million non-cached input, cached input and output tokens); for Gemini models, token counts at Google Gemini API rates (output includes thinking; {google_en} per million, same order). E is one value per plan category, not per model: Claude {cost['e_claude']} (1 by definition), Codex {cost['e_gpt']} (used for Sol and Luna alike), both read from the author's task-point history on {cost['plan_checked']}; Gemini {cost['e_gemini']} is an estimate from a 2026-11-16 analysis whose coverage (32 to 48%) is below the display threshold of the author's status page, and it will not be updated because the Antigravity tracking was removed. DeepSeek and Strata are not subscriptions and stay in actual-cost dollars, so they are not on the same footing as the plan runs. Strata uses work time × ({cost['watts']} W × {cost['electricity']} per kWh, the world household average, plus {cost['upkeep']} per hour of upkeep), excluding hardware purchase. Prices were checked on {cost['checked']}.",
            "method_missing": "Missing values are not zero: a task mean uses only the runs with data, and the notes under each chart list where that happens. Values marked ≥ are lower bounds, for example DeepSeek costs that miss requests dropped by a time-limit reminder.",
            "google_prices": "Google pricing", "openai_prices": "OpenAI pricing", "deepseek_prices": "DeepSeek pricing",
            "anthropic_prices": "Anthropic pricing", "electricity_prices": "Electricity prices",
            "footer_name": "Reviewer Model Benchmark",
            "footer_copyright": "© 2026 Tranzvision",
            "read_label": "How to read",
        },
        "zh": {
            "brand": "Reviewer\n模型基准",
            "topbar_context": "模型表现概览", "nav_label": "页面索引",
            "nav_overview": "概览", "nav_score": "综合分数",
            "nav_tradeoffs": "权衡比较", "nav_cost_score": "费用与分数",
            "nav_time_score": "耗时与分数", "nav_time_cost": "耗时与费用",
            "nav_reviewers": "任务分项",
            "nav_reviewer_score": "评分", "nav_reviewer_time": "耗时",
            "nav_reviewer_tokens": "Token 用量", "nav_reviewer_cost": "费用",
            "nav_reviewer_speed": "速度",
            "nav_method": "方法与数据",
            "eyebrow": "模型比较 / 基准",
            "headline": "AI 软件审查模型对比",
            "lead": "Reviewer 是负责一项软件审查任务的 AI 代理. 这里让 {model_count} 个模型通过 Codex 和 Claude Code 两种代理程序, 以不同推理强度完成四类任务, 比较完成任务的能力、耗时和费用.",
            "version_title": f"基准版本 v{PAGE_VERSION}",
            "version_summary": f"在 v2.0 测量 (新的模型、两种代理程序、评分 {SCORING_VERSION} 且分数可为负) 上, 加入晚一天补测的 GPT-6 Luna xhigh 和 max 推理强度, 以及晚约三周补测的 Gemini 4 Hydrogen low、medium、high 和 xhigh 推理强度 (在 Antigravity 代理程序中运行, low 比其余三档晚一天). 每个任务格计入 {runs['zh_range']} 次计分运行. v2.4 至 v2.6 只改了费用口径, 数据不变: 所有套餐运行 (Claude, GPT 与 Gemini 模型) 现在都换算成订阅价格, 即占 Claude $100 套餐周费用 ({cost['week_usd']}) 的份额, 份额经等效任务点求得 (v2.4 只有 Claude 与 GPT 按其占 $100 套餐周额度的比例计价; v2.5 把所有套餐运行显示为 Claude API 美元; v2.6 又回到套餐费用, 套餐运行之间的比例与 v2.5 相同). DeepSeek 与 Strata 仍按实际花费的美元计. 结果不能与 v1 直接比较.",
            "version_readme": "测量规则请见项目",
            "stat_models": "模型", "stat_configurations": "模型配置",
            "stat_benchmarks": "REVIEWER 任务", "stat_runs": "计分运行",
            "readme_more": "详情请见项目",
            "score_kicker": "01 / 质量", "score_title": "按推理强度比较综合分数",
            "score_desc": "同一代理程序上的每个模型为一组, 组内柱子按推理强度从高到低排列. 每根柱子背后的浅色底槽代表 0 至 100 的完整刻度, 柱高直接表示绝对能力; 须线表示 95% 置信区间.",
            "score_context": "推理强度标签是请求设置, 不代表不同模型使用了相同的计算量. 这些任务以 Claude Opus 标定, 报告也由 Opus 裁决, 所以 Opus 的位置可能偏高. 基准自身的报告只给分任务结果; 综合分数是本页对它们的汇总.",
            "score_models": "DeepSeek V4.1 Flash 是 DeepSeek 端点的 deepseek-flash 模型, 版本为 DeepSeek-V4.1-Flash-1017. Strata IQ3_XXS 是 Qwen3.8-Flash-Next 的 3 比特量化版本, 在一张 RTX 3080 Ti (12 GB) 上本地运行.",
            "score_read": "每组是一个代理程序上的一个模型, 每根柱子是一档推理强度. 底槽上方的数字是综合分数, 越高越好. 报告中的错误发现多于正确发现时, 分数会低于 0. 此结果只反映这些审查任务, 不代表模型的通用能力.",
            "trade_kicker": "02 / 权衡", "trade_title": "质量, 耗时与费用",
            "trade_intro": "每个点代表一个配置. 连线连接同一代理程序上同一模型的不同推理强度: 圆点为 Codex, 菱形为 Claude Code. 对前沿上的点, 其他可见点无法在两项指标上都不差、且至少一项更好. 点击图例中的帕累托前沿, 即可显示这些点及其连线. 按住 Ctrl 并在图表上滚动滚轮可缩放.",
            "cost_score_title": "单次运行费用与分数",
            "cost_score_desc": f"单次运行费用先对每项任务的单次费用求平均, 再对四项任务求平均. 各厂商的计费依据不同, 都不是实际账单: 所有套餐运行 (Claude, GPT 与 Gemini 模型) 按该次运行用掉的 Claude $100 套餐周费用 ({cost['week_usd']}) 的份额; DeepSeek 按逐请求价格; 本地 Strata 模型按估算的电费和维护费.",
            "cost_score_read": "分数越高越好; 越靠左表示单次运行费用越低. 悬停在点上可查看数值, ≥ 表示下限. 提示中的费用只有一个可比较的值: 套餐运行 (Claude, GPT, Gemini) 是换算成套餐订阅费后的价格, DeepSeek 与 Strata 是实际花费. 换算用同一条规则: 用掉 $100 套餐周额度 1/100 的运行, 费用就是周费用的 1/100 (见数据说明). 可用图表上方的线性 / 对数切换费用坐标: 线性便于比较绝对费用差异, 对数便于查看跨数量级的费用.",
            "time_score_title": "耗时与分数",
            "time_score_desc": "比较各配置的综合分数与单次审查运行的平均耗时.",
            "time_score_read": "分数越高越好; 越靠左表示单次运行越快. 耗时不含准备与加载. Codex 计代理的累计工作时间, Claude Code 计会话的墙钟时间. Code Spec 与 Code Standards 按各配置自身速度设定时限, 并限制在 15 至 60 分钟之间; 到时被停止的运行作废并重跑, 因此计入的运行都在时限内结束. 两点说明: 15 至 60 分钟规则之前完成的运行沿用当时的时限 (作废的运行随后以 60 分钟重跑, 其中一部分用了较新的 Claude Code 版本); DeepSeek-flash max 的 Code Spec (Claude Code) 一格只有 4 个计入的运行而不是 5 个, 因为它的重跑没能进行.",
            "time_cost_title": "耗时与单次运行费用",
            "time_cost_desc": "查看运行耗时与费用之间的关系.",
            "time_cost_read": "越靠左表示单次运行越快; 越靠下表示单次运行费用越低. 提示中的费用 (换算成套餐订阅费的价格, 或实际花费) 见“单次运行费用与分数”图的说明. 此图不表示质量, 需结合分数图阅读. 可用图表上方的线性 / 对数切换费用坐标.",
            "cost_scale": "费用坐标", "scale_linear": "线性", "scale_log": "对数",
            "review_kicker": "03 / 任务明细", "review_title": "按 Reviewer 任务比较",
            "review_desc": "分别比较各配置在四项 Reviewer 任务中的分数、耗时、token 用量、费用与速度.",
            "detail_score_title": "任务分数",
            "detail_time_title": "各任务的耗时",
            "detail_token_title": "各任务的 token 用量",
            "detail_cost_title": "各任务的费用",
            "detail_speed_title": "各任务的速度",
            "speed_label": "速度",
            "speed_task_output": "任务输出", "speed_task_input": "任务输入",
            "speed_engine_output": "引擎输出", "speed_engine_input": "引擎输入",
            "detail_score_read": f"每根柱子是基准计入的运行的平均分. 各格计分运行数: {runs['zh_counts']}. 底槽上方的数字是平均分, 须线表示 95% 置信区间; 只有约 5 次运行时, 低于约 30 分的差距可能只是波动. 标签颜色对应模型, 水平滚动可查看全部配置.",
            "detail_time_read": "每根柱子是该任务单次运行的平均耗时. Spec Readiness 每次运行有两个独立审查线程, 耗时相加.",
            "detail_token_read": "每根柱子从下到上叠加单次运行的平均未缓存输入、缓存输入和输出 token. Claude Code 把缓存写入计为未缓存输入; Codex 上的 Strata 含 guardian 请求. 悬停可查看准确数量.",
            "detail_cost_read": "每根柱子是该任务单次运行的平均费用. OpenAI, Claude 与 Gemini 为套餐运行, 费用按占 Claude $100 套餐周费用的份额计 (即换算成套餐订阅费的价格, 换算方法见数据说明). DeepSeek 与 Strata 按实际花费的美元计 (见数据说明). 可用图表上方的线性 / 对数切换费用坐标.",
            "detail_speed_read": "速度一律是总 token 除以总耗时, 不对各次运行的速度求平均. 任务速度是未缓存输入或输出 token 除以耗时, 即用户感受到的速度. 引擎速度只衡量模型本身. API 模型无法分出输入处理时间, 所以引擎输入速度未知, 引擎输出速度是下限 (≥); 只有 Strata 有引擎输入速度.",
            "reviewer_guide_title": "四项 Reviewer 任务及评分占比",
            "score_share_label": "评分占比",
            "reviewer_standards": "对照仓库指令与实现质量标准, 审查代码变更.",
            "reviewer_spec": "检查代码变更是否准确、完整地落实任务提供的要求.",
            "reviewer_audit": "审计暂存的提交候选: 选中的文件、必要检查和任务要求的覆盖情况.",
            "reviewer_readiness": "在实施前检查需求文档是否完整、一致、可实现且可验证. 每次运行有两个独立审查线程.",
            "method_kicker": "数据说明", "method_title": "分数与费用的计算方法",
            "method_selection": f"数据是基准的逐次运行结果. 本页使用基准主统计计入的运行. 各格计分运行数: {runs['zh_counts']}. GPT-6 Luna xhigh 和 max 是晚一天的补测, 计入全部有效运行, 基准本身不拿它们与其他配置比较. Gemini 4 Hydrogen low、medium、high 和 xhigh 是晚约三周的补测 (low 比其余三档晚一天), 使用另一种代理程序 (Antigravity, 部分运行为 1.5.8 版, 部分为 1.5.9 版), 计入全部有效运行, 基准同样不拿它们与其他配置比较. 在相同时限下由端点按 high 执行的 DeepSeek medium 请求并入 high. 无效运行, 以及时限不同而单列的 DeepSeek medium 请求补充配置, 都不计入. 题目套件是冻结的 ARW 760007c 加补丁, 计分 r8.4; 快照的来源记在 sources.json.",
            "method_score": f"单次运行的分数 (评分 {SCORING_VERSION}) 按报告找到的答案键问题加分, 按错误发现扣分. 分数不在 0 处截断, 所以可以为负; 没有产出报告的运行记 0 分. 任务分数是各次运行的平均值, 95% 区间按 t 分布计算. 综合分数 = 100 × ({weights}); 其区间合并四项的标准误, 自由度按 Welch–Satterthwaite 计算.",
            "method_runtime": "耗时和 token 对全部计入的运行求平均, 包括 0 分运行, 因为它们同样消耗了资源. 任务的值是有数据的运行的平均值; 配置的值是四项任务的值的算术平均. 速度是总 token 除以总耗时, 不对速度求平均: 任务速度合并该任务的各次运行.",
            "method_cost": f"单次运行费用: DeepSeek 采用基准按官方价逐请求计算的费用; Claude, GPT 与 Gemini 模型为套餐运行, 都换算成同一个订阅价格, 即 Claude $100 套餐的周费用 ({cost['week_usd']}: 每月 $100, 按 30 天一个月折成每天再乘 7 天). 一次运行的费用 = 它用掉的该套餐周额度的份额 × 周费用. 例如同一个 $100 套餐一周可跑小模型 10G token, 大模型只能跑 1G, 两者各实际用 100M token 时, 分别用掉周额度的 1/100 和 1/10, 费用就是周费用的 1/100 和 1/10. 份额通过等效任务点求得: 1 点是固定的 {cost['point_usd']} Claude API 花费, Claude $100 套餐一周有 {cost['week_points']} 点 (约 {cost['week_api']} 的 Claude API 标价用量, {cost['week_checked']} 实测), 套餐类别的效率比 E 是 Claude 做同类已完成的活会花的钱除以该套餐实际花的钱 (取自作者自己的使用历史). 一次运行的点数 = API 等价费用 × E ÷ {cost['point_usd']}, 费用 = 点数 ÷ {cost['week_points']} × {cost['week_usd']}. API 等价费用: Claude 模型用 Claude Code 报告的费用; GPT 模型按 OpenAI Standard API 单价换算 token ({rates_zh}); Gemini 模型按 Google Gemini API 单价换算 token (输出含思考; {google_zh}, 顺序同上). E 每个套餐类别一个值, 不按模型区分: Claude {cost['e_claude']} (按定义为 1), Codex {cost['e_gpt']} (Sol 与 Luna 通用), 均取自作者 {cost['plan_checked']} 的任务点历史; Gemini {cost['e_gemini']} 是 2026-11-16 一次分析的估算值, 覆盖率 (32% 至 48%) 低于作者状态页的显示门槛, 且 Antigravity 的统计已撤除, 不会再更新. DeepSeek 与 Strata 不是订阅, 仍按实际花费的美元计, 与套餐运行口径不同. Strata 按耗时 × ({cost['watts']} W × 全球家庭平均电价 {cost['electricity']}/kWh + 每小时维护费 {cost['upkeep']}) 计算, 不含硬件购置. 价格已于 {cost['checked']} 核对.",
            "method_missing": "缺失值不是 0: 任务均值只用有数据的运行, 各图下方的说明会列出这些情况. 标 ≥ 的值是下限, 例如 DeepSeek 有请求因时限提醒被丢弃而未计入的费用.",
            "google_prices": "Google 价格", "openai_prices": "OpenAI 价格", "deepseek_prices": "DeepSeek 价格",
            "anthropic_prices": "Anthropic 价格", "electricity_prices": "电价",
            "footer_name": "Reviewer 模型基准",
            "footer_copyright": "© 2026 Tranzvision",
            "read_label": "如何阅读",
        },
    }


SOURCE_LINKS = (
    ("google_prices", "https://ai.google.dev/gemini-api/docs/pricing"),
    ("openai_prices", "https://developers.openai.com/api/docs/pricing"),
    ("deepseek_prices", "https://api-docs.deepseek.com/quick_start/pricing/"),
    ("anthropic_prices", "https://www.anthropic.com/pricing"),
    ("electricity_prices", "https://www.globalpetrolprices.com/electricity_prices/"),
)


V2_ARM_ORDER = ("sol", "terra", "luna", "opus", "sonnet", "haiku", "hydrogen", "neon", "dsflash", "glm", "strata")
V2_ARM_NAMES = {"sol": "GPT-6.2 Sol", "terra": "GPT-6.1 Terra", "luna": "GPT-6 Luna", "opus": "Claude Opus 5.5",
                "sonnet": "Claude Sonnet 5.5", "haiku": "Claude Haiku 5.5", "hydrogen": "Gemini 4 Hydrogen",
                "neon": "Gemini 4 Neon", "dsflash": "DeepSeek V4.1 Flash", "glm": "GLM 5.3", "strata": "Strata IQ3_XXS"}
V2_CLI_NAMES = {"codex": "Codex", "claude": "Claude Code", "agy": "Antigravity"}
V2_SCENARIO_NAMES = {"code-standards": "Code Standards", "code-spec": "Code Spec", "commit-audit": "Commit Audit",
                     "spec-readiness": "Spec Readiness"}


def v2_overrides(copy, records, meta, pricing):
    """Replace the v1 wording with v2's in both languages. Wording not named here is shared by both suites."""
    runs = run_count_method_values(records)
    total = sum(cell["n"] for record in records for cell in record["cells"].values())
    failures, retries = meta["failures"], sum(arm["retries"] or 0 for arm in meta["arms"].values())
    plans = pricing["planCost"]["plans"]
    days = pricing["planCost"]["daysPerMonth"]
    fee = {vendor: usd(round(plan["monthlyUsd"] / days * 7, 2)) for vendor, plan in plans.items()}
    quota = {vendor: usd(plan["weeklyApiUsd"]) for vendor, plan in plans.items() if "weeklyApiUsd" in plan}
    oc = {model: round(plan_weekly_api_usd(plans["opencode"], model, days), 2) for model in plans["opencode"]["monthlyApiUsdByModel"]}
    checked = pricing["planCost"]["checkedAt"]
    en, zh = copy["en"], copy["zh"]
    en.update({
        "lead": ("A Reviewer is an AI agent assigned a software review task. Here, {model_count} models run four such "
                 "tasks through three agent harnesses, Codex, Claude Code and Antigravity, at different reasoning effort "
                 "settings; the charts compare their task performance, time and cost."),
        "version_title": f"Benchmark v2 · page {V2_PAGE_VERSION}",
        "version_summary": (f"Benchmark v2 is a new run: the {total} scored runs here (5 per task cell) were made on the same "
                            f"four tasks with a newer scoring ({V2_SCORING_VERSION}), a blind judge (GPT-6.2 Sol, high effort, "
                            "itself one of the tested models) and new models (GPT-6.2 Sol, GPT-6.1 Terra, Gemini 4 Neon, GLM 5.3). "
                            "Its scores are not comparable with v1, whose judge was Claude Opus; the v1 page stays online as an archive."),
        "score_context": ("Effort labels are requested settings, not equal compute across models. The reports were judged "
                          "blind (the judge did not see which model wrote which report) by GPT-6.2 Sol at high effort, which is also "
                          "a tested model; the judge's own agreement with a second reading of anchor pools was 1.0. GPT-6.1 Terra's "
                          "Code Spec and Code Standards cells are reruns with a corrected handoff (ARW 068d885); every other model's "
                          "two cells ran with the original handoff (see Data notes)."),
        "score_models": ("DeepSeek V4.1 Flash and GLM 5.3 ran through OpenCode Go in the Codex harness. Strata IQ3_XXS is a "
                         "3-bit quantization of Qwen3.8-Flash-Next run locally on one RTX 3080 Ti (12 GB), with only 20 runs (one effort, 5 per task)."),
        "cost_score_desc": ("Cost per run averages each task's per-run cost, then the four tasks. The bases differ by vendor "
                            "and none is an actual bill: for every subscription-plan run (Claude, GPT, Gemini, and DeepSeek and GLM "
                            "through OpenCode Go), the run's API-equivalent cost as a share of that plan's weekly quota, times the "
                            f"plan's weekly fee (Claude Max 20x {fee['anthropic']}, Codex $200 plan {fee['openai']}, Gemini $200 plan {fee['google']}, "
                            f"OpenCode Go {fee['opencode']}); and for the local Strata model, estimated electricity and upkeep."),
        "cost_score_read": ("Higher score is better; farther left is a lower cost per run. Hover a point for its values. "
                            "Each plan's weekly quota differs, so plan runs are priced against their own plan, and Strata is running cost: compare "
                            "across those groups with care (see Data notes). Use Linear / Log above the chart to switch the cost axis."),
        "time_score_read": ("Higher score is better; farther left is a shorter run. Work time excludes setup and loading. "
                            "Codex counts the agent's accumulated work time; Claude Code and Antigravity the session's wall time. "
                            "A void run (a harness fault or a time-limit stop) is rerun and not counted."),
        "time_cost_read": ("Farther left is a shorter run; lower is a lower cost per run. The cost bases differ by vendor "
                           "(see Cost per run vs. score). This plot does not encode quality, so use it alongside the score charts."),
        "detail_token_read": ("Each bar stacks mean non-cached input, cached input and output tokens per run. Claude Code counts "
                              "cache writes as non-cached input; Strata on Codex includes its guardian requests. Hover for exact counts."),
        "detail_cost_read": ("Each bar is one task's mean cost per run. Claude, GPT, Gemini, DeepSeek and GLM runs used subscriptions, so "
                             "theirs are the run's share of its own plan's weekly quota times that plan's weekly fee; Strata is running cost "
                             "(see Data notes). Use Linear / Log above the chart to switch the cost axis."),
        "detail_speed_read": ("A speed is total tokens divided by total seconds, never an average of per-run speeds. Task "
                              "speeds divide non-cached input or output tokens by work time: the speed a user perceives. "
                              "v2 reports only these two task speeds."),
        "method_selection": (f"The data are ARW's exported per-run results, scored by ARW scoring {V2_SCORING_VERSION}. Scored runs per cell: "
                             f"{runs['en_counts']}. {retries} runs were repeated after a harness fault or a void (they are listed per arm "
                             f"below); {failures} runs ended without a usable report and count as 0. "
                             "A run is counted when it is valid and scored; 700 runs were scored in total."),
        "method_score": (f"A run's score (scoring {V2_SCORING_VERSION}) credits the answer-key problems a report finds and deducts "
                         "its false findings. It is not cut at 0, so it can be negative, and a run that produced no report scores 0. "
                         f"A task score is the mean of its 5 runs, with a 95% interval from the t distribution. The weighted score is "
                         f"100 × (0.20 Code Standards + 0.20 Code Spec + 0.25 Commit Audit + 0.35 Spec Readiness); its interval "
                         "combines the four standard errors with Welch–Satterthwaite degrees of freedom."),
        "method_cost": ("Cost per run: Claude, GPT, Gemini, DeepSeek V4.1 Flash and GLM 5.3 models ran on subscription plans, and each run is priced "
                        "against the plan it used: cost = the run's API-equivalent cost ÷ the plan's weekly quota (in API-equivalent dollars) × the "
                        "plan's weekly fee, where the weekly fee is the monthly price over a 30-day month, times 7 days. "
                        f"Claude uses Max 20x ({usd(plans['anthropic']['monthlyUsd'])} a month, {fee['anthropic']} a week; weekly quota {quota['anthropic']}, "
                        "the status-page reading of the local Max 20x plan on 2026-11-26). "
                        f"Codex uses the $200 plan ({usd(plans['openai']['monthlyUsd'])} a month, {fee['openai']} a week); only a $100 plan was available, so its weekly "
                        f"quota {quota['openai']} is twice the $100 plan's measured one (the $200 plan is taken as double). "
                        f"Gemini uses a $200 plan ({usd(plans['google']['monthlyUsd'])} a month, {fee['google']} a week; weekly quota {quota['google']}, provided by the author 2026-11-26). "
                        f"DeepSeek and GLM use OpenCode Go ({usd(plans['opencode']['monthlyUsd'])} a month, {fee['opencode']} a week); its weekly allowance depends on the model "
                        f"(DeepSeek V4.1 Flash {usd(oc['deepseek-v4.1-flash'])}, GLM 5.3 {usd(oc['glm-5.3'])}, the monthly limit OpenCode publishes for each, divided by 30 and times 7). "
                        "Because every run is divided by its plan's quota and multiplied by its plan's fee, the efficiency of a plan (what a "
                        "dollar of API price buys of the plan) is built into the cost, and no further factor is applied. "
                        "The API-equivalent cost is, for Claude, each saved request's tokens at Anthropic's list price "
                        "(cache writes at the one-hour rate, Haiku above 100,000 prompt tokens at its long-prompt rate); for GPT and Gemini, token "
                        f"counts at the vendors' list prices; for DeepSeek and GLM, each request at the list price (DeepSeek at its peak and off-peak rates). "
                        "The weekly quotas are readings of the author's plans and carry some error (the Claude and Codex readings about a few percent), so "
                        "small differences between vendors are not meaningful. Strata uses work time × (400 W × $0.174 per kWh plus $0.02 per hour of "
                        f"upkeep), excluding hardware purchase. Prices and plan fees were checked on {checked}."),
        "method_missing": ("Missing values are not zero: a task mean uses only the runs with data, and the notes under each "
                           "chart list where that happens."),
        "v2_pools_title": "Judging pools",
        "v2_pools": ("The blind judge compares reports in pools. For Code Spec, Code Standards and Spec Readiness, one group of "
                     "reports was larger than the judge's pool limit, so those pools were built in 3 batches by repeat number; "
                     "anchor reports shared by the batches check that the three batches judge consistently (agreement 1.0 across the 127 pools)."),
        "v2_lists_title": "Finding lists",
        "v2_lists": ("The judge sorted the findings of each report into supported (1184) and contested-unsupported (275). These two "
                     "lists were not reviewed by hand; the scores use them as the judge produced them."),
        "v2_gpt_title": "GPT-6.1 Terra handoff",
        "v2_gpt": ("GPT-6.1 Terra refused all 30 runs of Code Spec and Code Standards under the original handoff, which gave no request "
                   "file. Its counted results for those two tasks come from a rerun with a corrected handoff (ARW commit 068d885, the "
                   "revcap-handoff fix applied on the 6ca23a9 pin; it is also in ARW 394029c); "
                   "all other cells use the original handoff (ARW commit 6ca23a9)."),
        "v2_strata_title": "Strata run.",
        "v2_strata": ("It ran on another machine with Codex 0.172.0, the other Codex arms with 0.171.0; its ARW commit is 104d038. "
                      "Seven of its 11 retries are not in the driver's void log and were restored from the saved attempt numbers."),
        "v2_arms_title": "Arms",
        "v2_arms_head": ("Arm", "Harness", "Runs", "Retries", "Unusable reports"),
        "v2_severity_title": "Answer-key points per task",
        "v2_severity_note": ("The table splits each task's answer-key points (the score's denominator) by severity. A score's "
                             "value does not depend on this split, because the report range is all three severities."),
        "v2_severity_head": ("Task", "High", "Medium", "Low"),
        "suite_label": "Suite:",
        "suite_link": "Open the v1 archive",
    })
    zh.update({
        "lead": ("Reviewer 是被安排做软件审核任务的 AI 代理. 这里 {model_count} 个模型通过三种代理程序 (Codex, Claude Code, "
                 "Antigravity), 在不同推理强度设置下完成四项这样的任务; 图表比较它们的任务表现, 耗时与费用."),
        "version_title": f"基准 v2 · 页面 {V2_PAGE_VERSION}",
        "version_summary": (f"基准 v2 是一次新的测量: 本页 {total} 次计分运行 (每个任务格 5 次) 做的是同样四项任务, 但使用了更新的评分 "
                            f"({V2_SCORING_VERSION}), 盲裁 (裁决者 GPT-6.2 Sol, high 强度, 它本身也是被测模型) 和新的模型 (GPT-6.2 Sol, "
                            "GPT-6.1 Terra, Gemini 4 Neon, GLM 5.3). 分数不能与 v1 比较 (v1 由 Claude Opus 裁决); v1 页面作为存档保留."),
        "score_context": ("推理强度标签是请求设置, 不代表不同模型使用了相同的计算量. 报告由 GPT-6.2 Sol (high 强度) 盲裁 (裁决者看不到报告出自哪个模型), "
                          "它也是被测模型; 对锚点池的二次阅读, 裁决一致率为 1.0. GPT-6.1 Terra 的 Code Spec 与 Code Standards 两格是用修正后的交接 "
                          "(ARW 068d885) 重跑的; 其他模型这两格用的是原交接 (见数据说明)."),
        "score_models": ("DeepSeek V4.1 Flash 与 GLM 5.3 通过 OpenCode Go 在 Codex 代理程序中运行. Strata IQ3_XXS 是 Qwen3.8-Flash-Next 的 "
                         "3 比特量化, 在一块 RTX 3080 Ti (12 GB) 上本地运行, 只有 20 次运行 (一个强度, 每项任务 5 次)."),
        "cost_score_desc": ("单次运行费用先对每项任务的单次费用求平均, 再对四项任务求平均. 各厂商口径不同, 都不是实际账单: 订阅套餐的运行 "
                            "(Claude, GPT, Gemini, 以及经 OpenCode Go 的 DeepSeek 与 GLM) 按该次运行的 API 等价费用占其所用套餐周额度的份额, 乘该套餐的周费用 "
                            f"(Claude Max 20x {fee['anthropic']}, Codex $200 套餐 {fee['openai']}, Gemini $200 套餐 {fee['google']}, OpenCode Go {fee['opencode']}); "
                            "本地 Strata 模型按估算的电费与维护费计."),
        "cost_score_read": ("分数越高越好, 越靠左单次费用越低. 悬停可看各点数值. 各套餐的周额度不同, 套餐运行按各自所用的套餐计价, Strata 是运行成本, "
                            "跨组比较要谨慎 (见数据说明). 用图上方的 Linear / Log 切换费用轴."),
        "time_score_read": ("分数越高越好, 越靠左单次运行越短. 工作时间不含准备与加载. Codex 计代理累计的工作时间; Claude Code 与 Antigravity "
                            "计会话的墙钟时间. 作废的运行 (代理程序故障或触到时限) 会重跑, 不计入."),
        "time_cost_read": ("越靠左单次运行越短, 越低单次费用越低. 各厂商费用口径不同 (见费用对分数一图). 这张图不含质量, 请与分数图一起看."),
        "detail_token_read": ("每根柱叠加单次运行平均的未缓存输入, 缓存输入与输出 token. Claude Code 把缓存写入计作未缓存输入; "
                              "Codex 上的 Strata 含其 guardian 请求. 悬停可看精确数字."),
        "detail_cost_read": ("每根柱是一项任务的单次平均费用. Claude, GPT, Gemini, DeepSeek 与 GLM 的运行用订阅, 所以按该次运行占其所用套餐周额度的份额乘该套餐周费用计; "
                             "Strata 是运行成本 (见数据说明). 用图上方的 Linear / Log 切换费用轴."),
        "detail_speed_read": ("速度是总 token 除以总秒数, 不对单次速度求平均. 任务速度用未缓存输入或输出 token 除以工作时间, 即用户感受到的速度. "
                              "v2 只给这两项任务速度."),
        "method_selection": (f"数据是 ARW 导出的逐次运行结果, 评分 {V2_SCORING_VERSION}. 各格计分运行数: {runs['zh_counts']}. 另有 {retries} 次运行因代理程序故障或作废重跑 "
                             f"(按组列在下面); {failures} 次运行没有可用报告, 计 0 分. 有效且已计分的运行才计入, 共 700 次."),
        "method_score": (f"单次运行的分数 (评分 {V2_SCORING_VERSION}) 按报告找到的答案键问题加分, 按错误发现扣分. 分数不在 0 处截断, 所以可以为负; "
                         "没有产出报告的运行记 0 分. 任务分数是 5 次运行的平均值, 95% 区间按 t 分布计算. 综合分数 = 100 × (0.20 Code Standards + "
                         "0.20 Code Spec + 0.25 Commit Audit + 0.35 Spec Readiness); 其区间合并四项的标准误, 自由度按 Welch–Satterthwaite 计算."),
        "method_cost": (f"单次运行费用: Claude, GPT, Gemini, DeepSeek V4.1 Flash 与 GLM 5.3 模型都是套餐运行, 每次运行按它所用的套餐计价: "
                        "费用 = 该次运行的 API 等价费用 ÷ 该套餐的周额度 (以 API 等价美元计) × 该套餐的周费用, 周费用是月价按 30 天一个月折成每天再乘 7 天. "
                        f"Claude 用 Max 20x (每月 {usd(plans['anthropic']['monthlyUsd'])}, 每周 {fee['anthropic']}; 周额度 {quota['anthropic']}, 取自状态页对本机 Max 20x 套餐 2026-11-26 的读数). "
                        f"Codex 用 $200 套餐 (每月 {usd(plans['openai']['monthlyUsd'])}, 每周 {fee['openai']}); 手头只有 $100 套餐, 所以周额度 {quota['openai']} 取 $100 套餐实测值的 2 倍 (按 $200 套餐是它的两倍计). "
                        f"Gemini 用 $200 套餐 (每月 {usd(plans['google']['monthlyUsd'])}, 每周 {fee['google']}; 周额度 {quota['google']}, 由作者于 2026-11-26 提供). "
                        f"DeepSeek 与 GLM 用 OpenCode Go (每月 {usd(plans['opencode']['monthlyUsd'])}, 每周 {fee['opencode']}); 它的周额度随模型而异 "
                        f"(DeepSeek V4.1 Flash {usd(oc['deepseek-v4.1-flash'])}, GLM 5.3 {usd(oc['glm-5.3'])}, 即 OpenCode 公布的各模型月限额除以 30 再乘 7). "
                        "每次运行都除以自己套餐的额度、乘自己套餐的费用, 所以各套餐的效率 (一美元 API 价格能换到多少套餐额度) 已包含在费用里, 不再另乘系数. "
                        "API 等价费用: Claude 按保存的逐请求 token 乘 Anthropic 标价 (缓存写入按一小时档, Haiku 提示超过 100,000 token 时按长提示档); "
                        "GPT 与 Gemini 按各厂商标价换算 token; DeepSeek 与 GLM 按逐请求标价 (DeepSeek 分峰谷价). "
                        "周额度是对作者所用套餐的读数, 带有一定误差 (Claude 与 Codex 的读数约几个百分点), 所以厂商之间的小差别没有意义. "
                        "Strata 按耗时 × (400 W × $0.174/kWh + 每小时维护费 $0.02) 计算, 不含硬件购置. "
                        f"价格与套餐费用已于 {checked} 核对."),
        "method_missing": "缺失值不是 0: 任务均值只用有数据的运行, 各图下方的说明会列出这些情况.",
        "v2_pools_title": "裁决分池",
        "v2_pools": ("盲裁者分池比较报告. Code Spec, Code Standards 与 Spec Readiness 各有一组报告超过裁决者的池上限, 所以这些池按重复序号分 3 批建立; "
                     "各批共用的锚点报告用来核对三批裁决是否一致 (127 个池一致率 1.0)."),
        "v2_lists_title": "发现列表",
        "v2_lists": "裁决者把各报告的发现分为有依据 (1184 条) 与有争议且无依据 (275 条). 这两张列表没有人工复核, 分数按裁决者给出的结果使用.",
        "v2_gpt_title": "GPT-6.1 Terra 的交接",
        "v2_gpt": ("原交接没有给出请求文件, GPT-6.1 Terra 在 Code Spec 与 Code Standards 上拒审了全部 30 次. 它这两项任务计入的成绩来自修正交接后的重跑 "
                   "(ARW 提交 068d885, 即 revcap-handoff 修正加在 6ca23a9 上, 同一修正也在 ARW 394029c 里); 其余各格都用原交接 (ARW 提交 6ca23a9)."),
        "v2_strata_title": "Strata 的运行.",
        "v2_strata": ("在另一台机器上用 Codex 0.172.0 运行, 其他 Codex 组为 0.171.0; 它的 ARW 提交是 104d038. "
                      "它的 11 次重跑中有 7 次不在驱动的作废记录里, 按保存的尝试序号补回."),
        "v2_arms_title": "各组",
        "v2_arms_head": ("组", "代理程序", "运行", "重跑", "无可用报告"),
        "v2_severity_title": "各任务答案键分值",
        "v2_severity_note": "表中把每项任务的答案键分值 (分数的分母) 按严重度拆开. 报告范围是全部三级, 所以分数不依赖这个拆分.",
        "v2_severity_head": ("任务", "高", "中", "低"),
        "suite_label": "基准套件:",
        "suite_link": "打开 v1 存档",
    })


def v2_flatten_heads(copy):
    """Table headers are tuples above; the language switch reads one text per key, so split them."""
    for texts in copy.values():
        for key in [k for k in texts if k.endswith("_head")]:
            for index, text in enumerate(texts.pop(key)):
                texts[f"{key}_{index}"] = text


def v2_notes_html(meta, records, en):
    """The v2-only data notes: pools, finding lists, handoffs, per-arm table, question counts (English first; the
    language switch swaps the text through data-i18n)."""
    def block(title_key, key):
        return (f'<p><strong data-i18n="{title_key}">{html.escape(en[title_key], quote=False)}</strong> '
                f'<span data-i18n="{key}">{html.escape(en[key], quote=False)}</span></p>')

    def table(title_key, head_key, rows, note_key=None):
        head = "".join(f'<th data-i18n="{head_key}_{i}">{html.escape(en[f"{head_key}_{i}"], quote=False)}</th>'
                       for i in range(5) if f"{head_key}_{i}" in en)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(cell), quote=False)}</td>" for cell in row) + "</tr>"
                       for row in rows)
        note = f'<p data-i18n="{note_key}">{html.escape(en[note_key], quote=False)}</p>' if note_key else ""
        return (f'<h3 data-i18n="{title_key}">{html.escape(en[title_key], quote=False)}</h3>{note}'
                f'<div class="table-scroll"><table class="data-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')

    arm_rows = []
    for lane in V2_ARM_ORDER:
        arm = meta["arms"].get(lane)
        if arm is None:
            continue
        harness = ", ".join(f"{V2_CLI_NAMES.get(h['cli'], h['cli'])} {h['version']}" for h in arm["harnesses"])
        arm_rows.append((V2_ARM_NAMES[lane], harness, arm["instances"],
                         "n/a" if arm["retries"] is None else arm["retries"], arm["modelFailures"]))
    severity_rows = []
    for scenario in ("code-standards", "code-spec", "commit-audit", "spec-readiness"):
        for name, info in meta["scenarios"].items():
            if name.endswith("/" + scenario):
                weights = info["severityWeights"]
                severity_rows.append((V2_SCENARIO_NAMES[scenario], weights["high"], weights["medium"], weights["low"]))
    return (block("v2_pools_title", "v2_pools") + block("v2_lists_title", "v2_lists")
            + block("v2_gpt_title", "v2_gpt") + block("v2_strata_title", "v2_strata")
            + table("v2_arms_title", "v2_arms_head", arm_rows)
            + table("v2_severity_title", "v2_severity_head", severity_rows, "v2_severity_note"))


def page(results, pricing, supplements=(), v2=None, assets=""):
    """Render the page. `assets` is the relative prefix of the resources/ directory (\"../\" one level down). `v2` is (records, meta) from stats.extract_v2; then `results` is unused and the page
    takes the v2 wording, the two task speeds and the extra data notes."""
    global SPEED_KEYS
    SPEED_KEYS = V2_SPEED_KEYS if v2 else V1_SPEED_KEYS
    records = v2[0] if v2 else extract(results, pricing, supplements)
    copy = page_copy(pricing, records)
    if v2:
        v2_overrides(copy, v2[0], v2[1], pricing)
        v2_flatten_heads(copy)
    else:
        copy["en"]["suite_banner"] = ("This is the archived v1 benchmark (scoring r8.4, Claude Opus as judge). "
                                      "The current benchmark is v2:")
        copy["zh"]["suite_banner"] = "这是已归档的 v1 基准 (评分 r8.4, 由 Claude Opus 裁决). 当前基准是 v2:"
        copy["en"]["suite_link"], copy["zh"]["suite_link"] = "Open v2", "打开 v2"
    model_count = len({record["model"] for record in records})
    run_count = sum(cell["n"] for record in records for cell in record["cells"].values())
    for language in ("en", "zh"):
        for key in ("headline", "lead"):
            copy[language][key] = copy[language][key].format(model_count=model_count)
        for metric in DETAIL_METRICS:
            copy[language][f"missing_{metric}_note"] = partial_note(records, metric, language)
    today = date.today()
    copy["en"]["footer_updated"] = f"Updated {today:%b} {today.day}, {today.year}"
    copy["zh"]["footer_updated"] = f"更新于 {today.year} 年 {today.month} 月 {today.day} 日"
    # Page text is plain text (the language switch sets textContent), so escape it as HTML.
    en = {key: html.escape(value, quote=False) for key, value in copy["en"].items()}

    def phrase(key, tag="span", class_name=""):
        css = f' class="{class_name}"' if class_name else ""
        return f'<{tag}{css} data-i18n="{key}">{en[key]}</{tag}>'

    def reading(key):
        return (f'<p class="reading-note"><strong data-i18n="read_label">{en["read_label"]}</strong> · '
                f'{phrase(key)}</p>')

    def missing(key):
        return phrase(key, "p", "metric-missing-note") if en[key] else ""

    suite_line = (f'<p class="suite-switch">{phrase("suite_label")} <strong>v2</strong> · '
                  f'<a href="v1/" data-i18n="suite_link">{en["suite_link"]}</a></p>' if v2 else
                  f'<p class="suite-switch">{phrase("suite_banner")} '
                  f'<a href="../" data-i18n="suite_link">{en["suite_link"]}</a></p>')
    extra_notes = v2_notes_html(v2[1], v2[0], en) if v2 else ""
    effort_html = effort_score_chart(records)
    grouped_html = task_score_chart(records)
    series_count = len({record["series"] for record in records})

    scatter_specs = (("cost", "score", "cost-score"),
                     ("minutes", "score", "time-score"),
                     ("minutes", "cost", "time-cost"))
    scatter_sections = []
    for index, (xkey, ykey, slug) in enumerate(scatter_specs, 1):
        cost_axis = "x" if xkey == "cost" else "y" if ykey == "cost" else None
        scale_html = cost_scale_control(f"benchmark-scatter-{index}", cost_axis) if cost_axis else ""
        scatter_sections.append(
            f'<article class="panel" id="{slug}">'
            f'<div class="chart-panel-heading">{phrase(slug.replace("-", "_") + "_title", "h3")}'
            f'{scale_html}</div>'
            f'{phrase(slug.replace("-", "_") + "_desc", "p", "chart-desc")}'
            f'<div class="plot-frame" id="benchmark-frame-{index}">'
            f'<div class="point-tooltip" id="benchmark-tooltip-{index}" hidden></div>'
            f'{chart(records, xkey, ykey, index)}</div>'
            f'{reading(slug.replace("-", "_") + "_read")}'
            f'{missing("missing_cost_note") if cost_axis else ""}</article>')
    detail_panels = []
    for metric in DETAIL_METRICS:
        name, anchor = DETAIL_METRICS[metric]["name"], DETAIL_METRICS[metric]["anchor"]
        control = ""
        if metric == "cost":
            control = cost_scale_control("benchmark-bars-cost", "y", default_scale="log")
        elif metric == "speed":
            control = segment_control(
                "speed-control",
                [(index, speed_key, en[speed_key]) for index, key in enumerate(SPEED_KEYS)
                 for speed_key in [f"speed_{key.replace('Output', '_output').replace('Input', '_input').lower()}"]],
                "speed", "speed_label", en["speed_label"])
        note = missing(f"missing_{metric}_note")
        detail_panels.append(
            f'<article class="panel" id="{anchor}">'
            f'<div class="chart-panel-heading">{phrase(f"detail_{name}_title", "h3")}{control}</div>'
            f'<div class="bar-tooltip" id="benchmark-bar-tooltip-{metric}" hidden></div>'
            f'<div class="bar-frame"><div class="bar-axis-overlay" aria-hidden="true" hidden></div>'
            f'<div class="bar-viewport"><div class="bar-scroll" style="--groups:{len(records)}">'
            f'{detail_bar_chart(records, metric)}</div></div></div>'
            f'{reading(f"detail_{name}_read")}{note}</article>')
    reviewer_guide = []
    guide_keys = ("reviewer_standards", "reviewer_spec", "reviewer_audit", "reviewer_readiness")
    guide_icons = ("standards", "spec", "audit", "readiness")
    for (_, name, weight), guide_icon, key in zip(REVIEWERS, guide_icons, guide_keys):
        reviewer_guide.append(
            f'<div class="reviewer-card"><div class="reviewer-card-title">'
            f'{icon(guide_icon, "reviewer-mark")}<strong>{name}</strong></div>'
            f'<div class="reviewer-card-meta">'
            f'<span>{phrase("score_share_label")}: <strong>{weight:.0%}</strong></span></div>'
            f'{phrase(key, "p")}</div>')
    source_links = "".join(
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{phrase(key)}'
        f'{icon("external", "external-mark")}</a>' for key, url in SOURCE_LINKS)
    readme_link = ('<a href="https://github.com/pellorao/reviewer-model-benchmark/blob/master/README.md" '
                   'data-href-en="https://github.com/pellorao/reviewer-model-benchmark/blob/master/README.md" '
                   'data-href-zh="https://github.com/pellorao/reviewer-model-benchmark/blob/master/README.zh-CN.md">README</a>')
    i18n_json = script_json(copy, ensure_ascii=False)
    speed_titles = {language: [SPEED_LABELS[key][index] for key in SPEED_KEYS]
                    for index, language in enumerate(("en", "zh"))}
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Reviewer Model Benchmark</title>
<meta name="benchmark-version" content="{V2_PAGE_VERSION if v2 else PAGE_VERSION}">
<meta name="benchmark-scoring-version" content="{V2_SCORING_VERSION if v2 else SCORING_VERSION}">
<link rel="icon" type="image/svg+xml" href="{assets}resources/favicon.svg">
<link rel="stylesheet" href="{assets}resources/fonts/fonts.css"><link rel="stylesheet" href="{assets}resources/site.css"></head><body><div class="app-shell">
<aside class="sidebar"><div class="brand">{icon('brand', 'brand-mark')}{phrase('brand')}</div><div><div class="side-label" data-i18n="nav_label">{en['nav_label']}</div><nav class="side-nav" aria-label="Page sections">
<a href="#overview" data-i18n="nav_overview" class="active">{en['nav_overview']}</a>
<a href="#score" data-i18n="nav_score">{en['nav_score']}</a>
<a href="#tradeoffs" data-i18n="nav_tradeoffs">{en['nav_tradeoffs']}</a>
<a href="#cost-score" class="sub" data-i18n="nav_cost_score">{en['nav_cost_score']}</a>
<a href="#time-score" class="sub" data-i18n="nav_time_score">{en['nav_time_score']}</a>
<a href="#time-cost" class="sub" data-i18n="nav_time_cost">{en['nav_time_cost']}</a>
<a href="#reviewers" data-i18n="nav_reviewers">{en['nav_reviewers']}</a>
<a href="#review-score" class="sub" data-i18n="nav_reviewer_score">{en['nav_reviewer_score']}</a>
<a href="#review-minutes" class="sub" data-i18n="nav_reviewer_time">{en['nav_reviewer_time']}</a>
<a href="#review-tokens" class="sub" data-i18n="nav_reviewer_tokens">{en['nav_reviewer_tokens']}</a>
<a href="#review-cost" class="sub" data-i18n="nav_reviewer_cost">{en['nav_reviewer_cost']}</a>
<a href="#review-speed" class="sub" data-i18n="nav_reviewer_speed">{en['nav_reviewer_speed']}</a>
<a href="#method" data-i18n="nav_method">{en['nav_method']}</a></nav></div>
</aside>
<main class="content"><div class="topbar">{phrase('topbar_context', 'span', 'topbar-context')}<div class="language-group" id="language-group" role="group" aria-label="Language"><button id="language-en" type="button" aria-pressed="true">English</button><button id="language-zh" type="button" aria-pressed="false">中文</button></div></div>
<section class="hero" id="overview">{suite_line}{phrase('eyebrow', 'div', 'eyebrow')}{phrase('headline', 'h1')}{phrase('lead', 'p', 'lead')}<div class="version-note">{phrase('version_title', 'strong')} {phrase('version_summary')} {phrase('version_readme')} {readme_link}.</div><div class="summary-strip"><div class="summary-item">{icon('models', 'summary-mark')}<strong>{model_count}</strong>{phrase('stat_models')}</div><div class="summary-item">{icon('configurations', 'summary-mark')}<strong>{len(records)}</strong>{phrase('stat_configurations')}</div><div class="summary-item">{icon('benchmark', 'summary-mark')}<strong>{len(REVIEWERS)}</strong>{phrase('stat_benchmarks')}</div><div class="summary-item">{icon('benchmark', 'summary-mark')}<strong>{run_count}</strong>{phrase('stat_runs')}</div></div></section>
<section class="chart-section" id="score"><div class="section-heading">{phrase('score_kicker', 'div', 'section-kicker')}{phrase('score_title', 'h2')}{phrase('score_desc', 'p')}<p class="section-context">{phrase('score_context')} {phrase('score_models')} {phrase('readme_more')} {readme_link}.</p></div>
<article class="panel"><div class="bar-tooltip" id="benchmark-bar-tooltip-effort" hidden></div><div class="bar-viewport"><div class="bar-scroll" style="--groups:{series_count}">{effort_html}</div></div>{reading('score_read')}</article></section>
<section class="chart-section" id="tradeoffs"><div class="section-heading">{phrase('trade_kicker', 'div', 'section-kicker')}{phrase('trade_title', 'h2')}{phrase('trade_intro', 'p')}</div>{''.join(scatter_sections)}</section>
<section class="chart-section" id="reviewers"><div class="section-heading">{phrase('review_kicker', 'div', 'section-kicker')}{phrase('review_title', 'h2')}{phrase('review_desc', 'p')}</div>
<div class="reviewer-guide">{phrase('reviewer_guide_title', 'h3', 'reviewer-guide-heading')}<div class="reviewer-grid">{''.join(reviewer_guide)}</div></div>
<article class="panel" id="review-score"><div class="chart-panel-heading">{phrase('detail_score_title', 'h3')}</div><div class="bar-tooltip" id="benchmark-bar-tooltip-grouped" hidden></div><div class="bar-frame"><div class="bar-axis-overlay" aria-hidden="true" hidden></div><div class="bar-viewport"><div class="bar-scroll" style="--groups:{len(records)}">{grouped_html}</div></div></div>{reading('detail_score_read')}</article>{''.join(detail_panels)}</section>
<section class="method-section" id="method"><div class="section-heading">{phrase('method_kicker', 'div', 'section-kicker')}{phrase('method_title', 'h2')}</div><div class="panel">{phrase('method_selection', 'p')}{phrase('method_score', 'p')}{phrase('method_runtime', 'p')}{phrase('method_cost', 'p', 'cost-note')}{phrase('method_missing', 'p')}{extra_notes}<div class="source-links">{source_links}</div></div></section>
</main></div><footer class="page-footer"><div class="footer-brand">{phrase('footer_name', 'span', 'footer-name')}{phrase('footer_copyright', 'span', 'footer-copyright')}</div>{phrase('footer_updated', 'span', 'footer-updated')}</footer><script>
const translations = {i18n_json};
// Tooltip titles end with the harness name, which is shown in a quieter gray.
function setTipTitle(element, label) {{
  const cut = label.lastIndexOf(' · ');
  const harness = label.slice(cut + 3);
  if (cut < 0 || !{script_json(list(HARNESS_NAMES.values()))}.includes(harness)) {{ element.textContent = label; return; }}
  element.textContent = label.slice(0, cut) + ' · ';
  const span = document.createElement('span');
  span.className = 'harness-name';
  span.textContent = harness;
  element.appendChild(span);
}}
window.chartLanguage = 'en';
const metricTitles = {{en:{{score:'{METRICS["score"][0]}',minutes:'{METRICS["minutes"][0]}',tokens:'Tokens per run',cost:'{METRICS["cost"][0]}'}},zh:{script_json(METRIC_LABELS_ZH, ensure_ascii=False)}}};
const speedTitles = {script_json(speed_titles, ensure_ascii=False)};
let speedIndex = 0;
const scatterAxes = [['cost','score'],['minutes','score'],['minutes','cost']];
const chartIds = ['benchmark-bars-effort','benchmark-scatter-1','benchmark-scatter-2','benchmark-scatter-3','benchmark-bars-grouped','benchmark-bars-minutes','benchmark-bars-tokens','benchmark-bars-cost','benchmark-bars-speed'];
function setLanguage(language) {{
  window.chartLanguage = language;
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = translations[language][element.dataset.i18n];
  for (const element of document.querySelectorAll('[data-href-en]')) element.setAttribute('href', element.getAttribute('data-href-' + language));
  document.getElementById('language-group').setAttribute('aria-label', language === 'en' ? 'Language' : '语言');
  document.getElementById('language-en').setAttribute('aria-pressed', String(language === 'en'));
  document.getElementById('language-zh').setAttribute('aria-pressed', String(language === 'zh'));
  for (const id of chartIds) document.getElementById(id)?.querySelectorAll('.hoverlayer').forEach(node => node.replaceChildren());
  document.querySelectorAll('.point-tooltip,.bar-tooltip').forEach(tip => {{ tip.hidden = true; }});
  scatterAxes.forEach(([x,y],index) => {{
    const gd = document.getElementById('benchmark-scatter-' + (index + 1));
    Plotly.relayout(gd, {{'xaxis.title.text':metricTitles[language][x], 'yaxis.title.text':metricTitles[language][y]}});
    Plotly.restyle(gd, {{name:[(language === 'en' ? 'Pareto Front' : '帕累托前沿') + {script_json(LEGEND_GAP)}]}}, [gd.data.length - 2]);
  }});
  for (const id of ['benchmark-bars-effort','benchmark-bars-grouped'])
    Plotly.relayout(document.getElementById(id), {{'yaxis.title.text':language === 'en' ? 'Score' : '分数'}});
  for (const [id,key] of [['benchmark-bars-minutes','minutes'],['benchmark-bars-tokens','tokens'],['benchmark-bars-cost','cost']])
    Plotly.relayout(document.getElementById(id), {{'yaxis.title.text':metricTitles[language][key]}});
  Plotly.relayout(document.getElementById('benchmark-bars-speed'), {{'yaxis.title.text':speedTitles[language][speedIndex]}});
  const tokenChart = document.getElementById('benchmark-bars-tokens');
  const tokenNames = language === 'en' ? ['Non-cached input','Cached input','Output'] : ['未缓存输入','缓存输入','输出'];
  Plotly.restyle(tokenChart, {{name:tokenNames.flatMap(name => Array({len(REVIEWERS)}).fill(name + {script_json(LEGEND_GAP)}))}});
  for (const control of document.querySelectorAll('.cost-scale-control'))
    control.setAttribute('aria-label', language === 'en' ? 'Cost axis scale' : '费用坐标尺度');
  requestAnimationFrame(() => chartIds.forEach(id => Plotly.Plots.resize(document.getElementById(id))));
}}
document.getElementById('language-en').addEventListener('click', () => {{ if (window.chartLanguage !== 'en') setLanguage('en'); }});
document.getElementById('language-zh').addEventListener('click', () => {{ if (window.chartLanguage !== 'zh') setLanguage('zh'); }});
const pressOnly = (control, button) => control.querySelectorAll('button').forEach(candidate =>
  candidate.setAttribute('aria-pressed', String(candidate === button)));
document.getElementById('speed-control').addEventListener('click', event => {{
  const button = event.target.closest('button[data-speed]');
  if (!button) return;
  pressOnly(event.currentTarget, button);
  speedIndex = Number(button.dataset.speed);
  const chart = document.getElementById('benchmark-bars-speed');
  Plotly.update(chart, {{visible:chart.data.map((_, index) => Math.floor(index / {len(REVIEWERS)}) === speedIndex)}},
    {{'yaxis.title.text':speedTitles[window.chartLanguage][speedIndex], 'yaxis.autorange':true}});
}});
function fitLogTickLabels(chart, axis, root = chart) {{
  const labels = [...root.querySelectorAll('.' + axis[0] + 'tick text')];
  for (const label of labels) label.style.removeProperty('visibility');
  if (chart._fullLayout[axis].type !== 'log') return;
  const horizontal = axis === 'xaxis';
  // Plotly offsets log labels starting with 0 or 1; keep one baseline or right edge.
  const coordinate = horizontal ? 'y' : 'x';
  const positions = labels.map(label => Number(label.getAttribute(coordinate))).filter(Number.isFinite);
  if (positions.length) {{
    const aligned = horizontal ? Math.max(...positions) : Math.min(...positions);
    for (const label of labels) label.setAttribute(coordinate, String(aligned));
  }}
  const gap = horizontal ? 8 : 4;
  // Fit labels to their rendered size while keeping Plotly's grid and tick positions.
  const candidates = labels.map(label => {{
    const bounds = label.getBoundingClientRect();
    const value = Number(label.textContent.replace(/[$,\\s]/g, '').replace('−', '-'));
    const exponent = Math.log10(value);
    return {{label, start:horizontal ? bounds.left : bounds.top,
      end:horizontal ? bounds.right : bounds.bottom,
      size:horizontal ? bounds.width : bounds.height,
      major:Number.isFinite(exponent) && Math.abs(exponent - Math.round(exponent)) < 1e-8}};
  }}).filter(candidate => candidate.size > 0);
  candidates.sort((a,b) => Number(b.major) - Number(a.major) || a.start - b.start);
  const kept = [];
  for (const candidate of candidates) {{
    if (kept.some(other => candidate.start < other.end + gap && candidate.end + gap > other.start))
      candidate.label.style.visibility = 'hidden';
    else kept.push(candidate);
  }}
}}
for (const control of document.querySelectorAll('.cost-scale-control')) {{
  const axis = control.dataset.axis + 'axis';
  const chart = document.getElementById(control.dataset.plot);
  chart.on('plotly_afterplot', () => fitLogTickLabels(chart, axis));
  fitLogTickLabels(chart, axis);
  const overlay = chart.closest('.bar-frame')?.querySelector('.bar-axis-overlay');
  if (overlay && !overlay.hidden) fitLogTickLabels(chart, axis, overlay);
  control.addEventListener('click', event => {{
    const button = event.target.closest('button[data-scale]');
    if (!button || button.getAttribute('aria-pressed') === 'true') return;
    Plotly.relayout(chart, {{[axis + '.type']:button.dataset.scale,
      [axis + '.dtick']:button.dataset.scale === 'log' ? 'D1' : null, [axis + '.autorange']:true}});
    for (const candidate of control.querySelectorAll('button[data-scale]'))
      candidate.setAttribute('aria-pressed', String(candidate === button));
  }});
}}
const navLinks = [...document.querySelectorAll('.side-nav a')];
const sections = navLinks.map(link => document.querySelector(link.getAttribute('href'))).filter(Boolean);
let clickedNavLink = null;
let navUpdatePending = false;
const activateNavLink = selected =>
  navLinks.forEach(link => link.classList.toggle('active', link === selected));
const updateNavFromScroll = () => {{
  if (clickedNavLink) return;
  const marker = window.innerHeight * .2;
  let current = sections[0];
  for (const section of sections) {{
    const bounds = section.getBoundingClientRect();
    if (bounds.top <= marker && bounds.bottom > marker) current = section;
    else if (bounds.top <= marker && current?.getBoundingClientRect().bottom <= marker)
      current = section;
  }}
  activateNavLink(navLinks.find(link => link.getAttribute('href') === '#' + current?.id));
}};
const requestNavUpdate = () => {{
  if (clickedNavLink || navUpdatePending) return;
  navUpdatePending = true;
  requestAnimationFrame(() => {{ navUpdatePending = false; updateNavFromScroll(); }});
}};
const releaseNavClick = () => {{ clickedNavLink = null; requestNavUpdate(); }};
for (const link of navLinks) link.addEventListener('click', () => {{
  clickedNavLink = link;
  activateNavLink(link);
}});
window.addEventListener('wheel', event => {{
  if (!event.target.closest('.sidebar')) releaseNavClick();
}}, {{capture:true, passive:true}});
window.addEventListener('touchstart', event => {{
  if (!event.target.closest('.sidebar')) releaseNavClick();
}}, {{passive:true}});
window.addEventListener('keydown', event => {{
  if (['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key))
    releaseNavClick();
}});
document.addEventListener('pointerdown', event => {{
  if (!event.target.closest('.side-nav')) releaseNavClick();
}});
window.addEventListener('scroll', requestNavUpdate, {{passive:true}});
document.fonts.ready.then(() => requestAnimationFrame(() =>
  chartIds.forEach(id => Plotly.Plots.resize(document.getElementById(id)))));
</script></body></html>"""


# Cloudflare Pages runs `build.py benchmark-results.json <dir>/index.html` (README "Publishing"; the dashboard
# command cannot change). An output named index.html therefore builds the published site: the current v2 page
# there and the archived v1 page in v1/ next to it, which reads the shared resources/ one level up.
SITE_INDEX = "index.html"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_json", nargs="?", type=Path,
                        default=Path(__file__).with_name("benchmark-results.json"))
    parser.add_argument("output", nargs="?", type=Path,
                        default=Path(__file__).with_name("charts.html"))
    parser.add_argument("--supplement", type=Path, action="append", default=None,
                        help="supplement-only results file (default: benchmark-results-phase4.json next to build.py)")
    parser.add_argument("--v2", nargs=2, type=Path, metavar=("EXPORT", "SUPPLEMENT"),
                        help="build the v2 page from an ARW export and its supplement file (results_json is ignored)")
    parser.add_argument("--pricing", type=Path, help="pricing file (default pricing.json; pricing-v2.json with --v2)")
    args = parser.parse_args(argv)
    supplements = args.supplement if args.supplement is not None else [
        path for path in [Path(__file__).with_name("benchmark-results-phase4.json")] if path.is_file()]
    here = Path(__file__).parent
    site = not args.v2 and args.output.name == SITE_INDEX  # the published-site command, see SITE_INDEX

    def build_v2(export_path, supplement_path):
        pricing = load_pricing(args.pricing or here / "pricing-v2.json")
        export_bytes = export_path.read_bytes()
        v2 = extract_v2(json.loads(export_bytes), json.loads(supplement_path.read_text(encoding="utf-8")), pricing,
                        hashlib.sha256(export_bytes).hexdigest())
        return page(None, pricing, (), v2)

    def build_v1(assets=""):
        return page(json.loads(args.results_json.read_text(encoding="utf-8")),
                    load_pricing(*([args.pricing] if args.pricing else [])),
                    [json.loads(path.read_text(encoding="utf-8")) for path in supplements], assets=assets)

    if args.v2:
        text = build_v2(*args.v2)
    elif site:
        text = build_v2(here / "snapshots/v2/export.json", here / "snapshots/v2/supplement.json")
        v1_output = args.output.parent / "v1" / SITE_INDEX
        v1_output.parent.mkdir(exist_ok=True)
        v1_output.write_text(build_v1(assets="../"), encoding="utf-8")
    else:
        text = build_v1()
    args.output.write_text(text, encoding="utf-8")
    favicon_path = args.output.parent / "resources" / "favicon.svg"
    if favicon_path.parent.is_dir():  # the default output has resources/; elsewhere it is not created
        favicon_path.write_text(favicon_svg(), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
