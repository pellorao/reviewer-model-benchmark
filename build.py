"""Build the offline Reviewer Model Benchmark page from local benchmark-results.json."""

import argparse
import colorsys
import html
import json
import math
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from stats import (EFFORTS, HARNESS_NAMES, MODEL_NAMES, REVIEWERS, SPEED_KEYS, TOKEN_KEYS,
                   extract, load_pricing)


PAGE_VERSION = "2.1"
SCORING_VERSION = "r8.4"
# Model colors in MODEL_NAMES order (stats.py); series follow harness order, then this model order.
MODEL_COLORS = {
    "gpt-6.1-sol": "#4c78b8",
    "gpt-6-luna": "#b47627",
    "opus": "#8659b9",
    "sonnet": "#bb5272",
    "haiku": "#198f76",
    "deepseek-flash": "#d07849",
    "strata-iq3_xxs": "#2f8fa9",
}
TOKEN_COLORS = {"uncachedInput": "#6388b7", "cachedInput": "#5f9e98", "output": "#b3935e"}
# Marker symbols per harness (names in stats.py); all effort lines are solid.
HARNESS_SYMBOLS = {"codex": "circle", "claude-code": "diamond"}
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
COST_BASIS = {
    "openai": ("Subscription run, reference API price", "套餐运行, 参考 API 价"),
    "deepseek": ("DeepSeek price per request", "DeepSeek 逐请求价格"),
    "anthropic": ("Subscription run, reference API price", "套餐运行, 参考 API 价"),
    "strata": ("Local running cost", "本地运行成本"),
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


def hover_summary(record, xkey, ykey):
    summary = (f"{record['label']}\n{short_value(record, xkey)}\n"
               f"{short_value(record, ykey)}")
    if "cost" in (xkey, ykey):
        # English and Chinese notes are tab-separated; the tooltip picks the page language.
        english, chinese = COST_BASIS[record["vendor"]]
        summary += f"\nCost: {english}\t费用: {chinese}"
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
    figure.update_layout(template="plotly_white", height=600, autosize=True,
                         margin={"l": 75, "r": 32, "t": 60, "b": 70},
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=CHART_PLOT,
                         font={"color": CHART_TEXT, "family": CHART_FONT},
                         legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0,
                                 "font": {"size": 11}, "groupclick": "togglegroup",
                                 # Fixed slots: measured widths overlap for long model · harness names.
                                 "entrywidth": 200, "entrywidthmode": "pixels"},
                         xaxis_title=METRICS[xkey][0], yaxis_title=METRICS[ykey][0],
                         hovermode="closest", dragmode="pan")
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
      if (notes.length) {
        const note = document.createElement('div');
        note.className = 'point-tip-note';
        note.textContent = notes.map(line => line.split(String.fromCharCode(9))[window.chartLanguage === 'zh' ? 1 : 0] ?? line)
          .join(String.fromCharCode(10));
        data.appendChild(note);
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
      tip.style.width = Math.ceil(Math.max(textWidth(title), cellWidth * 2) + 20) + 'px';
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


def score_layout(figure, y_range, **layout):
    figure.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor=CHART_PLOT, dragmode="pan",
                         font={"color": CHART_TEXT, "family": CHART_FONT},
                         yaxis_title="Score", yaxis_range=y_range, **layout)
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
            meta = (f"Weighted score ± 95% CI · {len(rows)} effort levels" if language == "en"
                    else f"综合分数 ± 95% 区间 · {len(rows)} 档推理强度")
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
    lower = (cell["speedLowerBounds"][speed] if metric == "speed"
             else cell["tokenLowerBound"] if metric == "tokens"
             else cell["costLowerBound"] if metric == "cost" else False)
    if lower:
        text += "\nIncludes lower bounds (≥)" if en else "\n含下限值 (≥)"
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
    figure.update_layout(barmode="stack" if metric == "tokens" else "group", bargap=0.18,
                         bargroupgap=0.10, template="plotly_white", height=600,
                         width=max(1200, len(xlabels) * 84),
                         margin={"l": 75, "r": 25, "t": 95, "b": 110},
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=CHART_PLOT,
                         font={"color": CHART_TEXT, "family": CHART_FONT},
                         legend={"orientation": "h", "y": 1.02, "yanchor": "bottom"},
                         yaxis_title=title, dragmode="pan")
    figure.update_xaxes(categoryorder="array", categoryarray=xlabels,
                        tickmode="array", tickvals=xlabels, ticktext=ticktext,
                        tickangle=0, tickfont={"size": 11})
    figure.update_yaxes(gridcolor=CHART_GRID, zerolinecolor="#c7bbaa",
                        tickfont={"family": CHART_FONT, "size": 11})
    if metric == "tokens":
        figure.update_yaxes(tickformat="~s")
    elif metric == "cost":
        figure.update_yaxes(type="linear", tickprefix="$", showtickprefix="all", tickformat=".3~g")
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
                          if speed != "engineInput" or record["vendor"] == "strata"]
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
    local = pricing["localRunningCost"]["strata-iq3_xxs"]
    return {"rates": rates, "watts": f"{local['wallPowerWatts']:g}",
            "electricity": usd(local["electricityUsdPerKwh"]),
            "upkeep": usd(local["maintenanceUsdPerHour"]), "checked": pricing["checkedAt"]}


def page_copy(pricing):
    weights = " + ".join(f"{weight:.2f} {name}" for _, name, weight in REVIEWERS)
    cost = cost_method_values(pricing)
    rates_en = join_and([f"{name} {rate}" for name, rate in cost["rates"]])
    rates_zh = ", ".join(
        f"{name} 每百万未缓存输入、缓存输入、输出 token 为 {rate}" if index == 0 else f"{name} 为 {rate}"
        for index, (name, rate) in enumerate(cost["rates"]))
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
            "version_summary": f"Adds GPT-6 Luna at xhigh and max effort, a supplement run one day later, to the v2.0 run (new models, two harnesses, scoring {SCORING_VERSION} with scores that can be negative, 5 to 10 scored runs per task). Results are not comparable with v1.",
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
            "cost_score_desc": "Cost per run averages each task's per-run cost, then the four tasks. The bases differ by vendor and none is an actual bill: DeepSeek per-request prices; for Claude models, the API-equivalent cost Claude Code reports (subscription run, reference API price); for GPT models, token counts at OpenAI API list prices (subscription run, reference API price); and estimated electricity and upkeep for the local Strata model.",
            "cost_score_read": "Higher score is better; farther left is a lower cost per run. Hover a point for its cost basis. Use Linear / Log above the chart to switch the cost axis: Linear shows absolute differences; Log helps compare costs across a wide range.",
            "time_score_title": "Work time vs. score",
            "time_score_desc": "Compare the weighted score with the average work time of one review run.",
            "time_score_read": "Higher score is better; farther left is a shorter run. Work time excludes setup and loading. Codex counts the agent's accumulated work time and Claude Code the session's wall time. Code Spec and Code Standards stop at a time limit set from each configuration's own speed.",
            "time_cost_title": "Work time vs. cost per run",
            "time_cost_desc": "Inspect the relationship between run time and cost.",
            "time_cost_read": "Farther left is a shorter run; lower is a lower cost per run. This plot does not encode quality, so use it alongside the score charts. Use Linear / Log above the chart to switch the cost axis.",
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
            "detail_score_read": "Each bar is the mean score of the runs the benchmark counts: 10 for Strata, 5 to 8 for GPT-6 Luna xhigh and max, and 5 for other configurations (8 for DeepSeek high in Commit Audit). The number above a track is the mean and the whisker the 95% confidence interval; with about five runs, a difference below about 30 points may be noise. The label color identifies the model. Scroll horizontally to compare all configurations.",
            "detail_time_read": "Each bar is one task's mean work time per run. Spec Readiness runs two independent review threads per run; their times are added.",
            "detail_token_read": "Each bar stacks mean non-cached input, cached input and output tokens per run. Claude Code counts cache writes as non-cached input; Strata on Codex includes its guardian requests. Hover for exact counts.",
            "detail_cost_read": "Each bar is one task's mean cost per run on the basis named in the tooltip; OpenAI and Claude runs used subscriptions, so theirs are reference API prices. Use Linear / Log above the chart to switch the cost axis.",
            "detail_speed_read": "A speed is total tokens divided by total seconds, never an average of per-run speeds. Task speeds divide non-cached input or output tokens by work time: the speed a user perceives. Engine speeds measure the model alone. API models cannot separate input processing, so their engine input speed is unknown and their engine output speed is a lower bound (≥); engine input speed exists only for Strata.",
            "reviewer_guide_title": "The four reviewer tasks and their score shares",
            "score_share_label": "Score share",
            "reviewer_standards": "Reviews code changes against repository instructions and implementation quality standards.",
            "reviewer_spec": "Checks whether code changes implement the requirements supplied for the task accurately and completely.",
            "reviewer_audit": "Audits a staged commit candidate: the selected files, required checks and coverage of the supplied requirements.",
            "reviewer_readiness": "Before implementation, checks whether requirement documents are complete, consistent, feasible and verifiable. Each run has two independent review threads.",
            "method_kicker": "DATA NOTES", "method_title": "How scores and costs are calculated",
            "method_selection": "The data are the benchmark's per-run results. The page uses the runs the benchmark counts in its main statistics: 10 per task for Strata and 5 for other configurations. GPT-6 Luna xhigh and max are a supplement run a day later with every valid run counted (5 to 8 per task); the benchmark does not compare them with other configurations. DeepSeek runs requested as medium count as high where the endpoint ran them as high under the same time limit, so DeepSeek high has 8 runs in Commit Audit. Invalid runs and the supplementary DeepSeek configuration requested as medium under a different time limit are excluded.",
            "method_score": f"A run's score (scoring {SCORING_VERSION}) credits the answer-key problems a report finds and deducts its false findings. It is not cut at 0, so it can be negative, and a run that produced no report scores 0. A task score is the mean of its runs, with a 95% interval from the t distribution. The weighted score is 100 × ({weights}); its interval combines the four standard errors with Welch–Satterthwaite degrees of freedom.",
            "method_runtime": "Time and tokens average every counted run, including zero-score runs, which still used resources. A task's value is the mean over its runs with data; a configuration's value is the arithmetic mean of its four task values. Speeds are total tokens over total seconds, never a mean of speeds: a task's speed pools its runs, and a configuration's speed pools one average run of each task.",
            "method_cost": f"Cost per run: DeepSeek uses the benchmark's per-request cost at official prices; Claude models use the API-equivalent cost reported by Claude Code (subscription run, reference API price); GPT models price their tokens at OpenAI Standard API rates (subscription run, reference API price) ({rates_en} per million non-cached input, cached input and output tokens); Strata uses work time × ({cost['watts']} W × {cost['electricity']} per kWh, the world household average, plus {cost['upkeep']} per hour of upkeep), excluding hardware purchase. Prices were checked on {cost['checked']}.",
            "method_missing": "Missing values are not zero: a task mean uses only the runs with data, and the notes under each chart list where that happens. Values marked ≥ are lower bounds, for example DeepSeek costs that miss requests dropped by a time-limit reminder.",
            "openai_prices": "OpenAI pricing", "deepseek_prices": "DeepSeek pricing",
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
            "version_summary": f"在 v2.0 测量 (新的模型、两种代理程序、评分 {SCORING_VERSION} 且分数可为负、每项任务计入 5 至 10 次运行) 上, 加入晚一天补测的 GPT-6 Luna xhigh 和 max 推理强度. 结果不能与 v1 直接比较.",
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
            "cost_score_desc": "单次运行费用先对每项任务的单次费用求平均, 再对四项任务求平均. 各厂商的计费依据不同, 都不是实际账单: DeepSeek 按逐请求价格; Claude 模型按 Claude Code 报告的 API 等价费用 (套餐运行, 参考 API 价); GPT 模型按 OpenAI API 标价换算 token (套餐运行, 参考 API 价); 本地 Strata 模型按估算的电费和维护费.",
            "cost_score_read": "分数越高越好; 越靠左表示单次运行费用越低. 悬停在点上可查看计费依据. 可用图表上方的线性 / 对数切换费用坐标: 线性便于比较绝对费用差异, 对数便于查看跨数量级的费用.",
            "time_score_title": "耗时与分数",
            "time_score_desc": "比较各配置的综合分数与单次审查运行的平均耗时.",
            "time_score_read": "分数越高越好; 越靠左表示单次运行越快. 耗时不含准备与加载. Codex 计代理的累计工作时间, Claude Code 计会话的墙钟时间. Code Spec 与 Code Standards 按各配置自身速度设定时限, 到时即停止.",
            "time_cost_title": "耗时与单次运行费用",
            "time_cost_desc": "查看运行耗时与费用之间的关系.",
            "time_cost_read": "越靠左表示单次运行越快; 越靠下表示单次运行费用越低. 此图不表示质量, 需结合分数图阅读. 可用图表上方的线性 / 对数切换费用坐标.",
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
            "detail_score_read": "每根柱子是基准计入的运行的平均分: Strata 10 次, GPT-6 Luna xhigh 和 max 5 至 8 次, 其他配置 5 次 (Commit Audit 中的 DeepSeek high 为 8 次). 底槽上方的数字是平均分, 须线表示 95% 置信区间; 只有约 5 次运行时, 低于约 30 分的差距可能只是波动. 标签颜色对应模型, 水平滚动可查看全部配置.",
            "detail_time_read": "每根柱子是该任务单次运行的平均耗时. Spec Readiness 每次运行有两个独立审查线程, 耗时相加.",
            "detail_token_read": "每根柱子从下到上叠加单次运行的平均未缓存输入、缓存输入和输出 token. Claude Code 把缓存写入计为未缓存输入; Codex 上的 Strata 含 guardian 请求. 悬停可查看准确数量.",
            "detail_cost_read": "每根柱子是该任务单次运行的平均费用, 计费依据见悬停提示; OpenAI 与 Claude 为套餐运行, 费用是参考 API 价. 可用图表上方的线性 / 对数切换费用坐标.",
            "detail_speed_read": "速度一律是总 token 除以总耗时, 不对各次运行的速度求平均. 任务速度是未缓存输入或输出 token 除以耗时, 即用户感受到的速度. 引擎速度只衡量模型本身. API 模型无法分出输入处理时间, 所以引擎输入速度未知, 引擎输出速度是下限 (≥); 只有 Strata 有引擎输入速度.",
            "reviewer_guide_title": "四项 Reviewer 任务及评分占比",
            "score_share_label": "评分占比",
            "reviewer_standards": "对照仓库指令与实现质量标准, 审查代码变更.",
            "reviewer_spec": "检查代码变更是否准确、完整地落实任务提供的要求.",
            "reviewer_audit": "审计暂存的提交候选: 选中的文件、必要检查和任务要求的覆盖情况.",
            "reviewer_readiness": "在实施前检查需求文档是否完整、一致、可实现且可验证. 每次运行有两个独立审查线程.",
            "method_kicker": "数据说明", "method_title": "分数与费用的计算方法",
            "method_selection": "数据是基准的逐次运行结果. 本页使用基准主统计计入的运行: Strata 每项任务 10 次, 其他配置 5 次. GPT-6 Luna xhigh 和 max 是晚一天的补测, 计入全部有效运行 (每项任务 5 至 8 次), 基准本身不拿它们与其他配置比较. 在相同时限下由端点按 high 执行的 DeepSeek medium 请求并入 high, 因此 Commit Audit 中的 DeepSeek high 有 8 次. 无效运行, 以及时限不同而单列的 DeepSeek medium 请求补充配置, 都不计入.",
            "method_score": f"单次运行的分数 (评分 {SCORING_VERSION}) 按报告找到的答案键问题加分, 按错误发现扣分. 分数不在 0 处截断, 所以可以为负; 没有产出报告的运行记 0 分. 任务分数是各次运行的平均值, 95% 区间按 t 分布计算. 综合分数 = 100 × ({weights}); 其区间合并四项的标准误, 自由度按 Welch–Satterthwaite 计算.",
            "method_runtime": "耗时和 token 对全部计入的运行求平均, 包括 0 分运行, 因为它们同样消耗了资源. 任务的值是有数据的运行的平均值; 配置的值是四项任务的值的算术平均. 速度是总 token 除以总耗时, 不对速度求平均: 任务速度合并该任务的各次运行, 配置速度合并每项任务的一次平均运行.",
            "method_cost": f"单次运行费用: DeepSeek 采用基准按官方价逐请求计算的费用; Claude 模型采用 Claude Code 报告的 API 等价费用 (套餐运行, 参考 API 价); GPT 模型按 OpenAI Standard API 单价换算 token (套餐运行, 参考 API 价) ({rates_zh}); Strata 按耗时 × ({cost['watts']} W × 全球家庭平均电价 {cost['electricity']}/kWh + 每小时维护费 {cost['upkeep']}) 计算, 不含硬件购置. 价格已于 {cost['checked']} 核对.",
            "method_missing": "缺失值不是 0: 任务均值只用有数据的运行, 各图下方的说明会列出这些情况. 标 ≥ 的值是下限, 例如 DeepSeek 有请求因时限提醒被丢弃而未计入的费用.",
            "openai_prices": "OpenAI 价格", "deepseek_prices": "DeepSeek 价格",
            "anthropic_prices": "Anthropic 价格", "electricity_prices": "电价",
            "footer_name": "Reviewer 模型基准",
            "footer_copyright": "© 2026 Tranzvision",
            "read_label": "如何阅读",
        },
    }


SOURCE_LINKS = (
    ("openai_prices", "https://developers.openai.com/api/docs/pricing"),
    ("deepseek_prices", "https://api-docs.deepseek.com/quick_start/pricing/"),
    ("anthropic_prices", "https://www.anthropic.com/pricing"),
    ("electricity_prices", "https://www.globalpetrolprices.com/electricity_prices/"),
)


def page(results, pricing):
    records = extract(results, pricing)
    copy = page_copy(pricing)
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
            control = cost_scale_control("benchmark-bars-cost", "y", default_scale="linear")
        elif metric == "speed":
            control = segment_control(
                "speed-control",
                [(index, f"speed_{key.replace('Output', '_output').replace('Input', '_input').lower()}",
                  en[f"speed_{key.replace('Output', '_output').replace('Input', '_input').lower()}"])
                 for index, key in enumerate(SPEED_KEYS)],
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
    readme_link = ('<a href="https://github.com/Traveller23/reviewer-model-benchmark/blob/master/README.md" '
                   'data-href-en="https://github.com/Traveller23/reviewer-model-benchmark/blob/master/README.md" '
                   'data-href-zh="https://github.com/Traveller23/reviewer-model-benchmark/blob/master/README.zh-CN.md">README</a>')
    i18n_json = script_json(copy, ensure_ascii=False)
    speed_titles = {language: [SPEED_LABELS[key][index] for key in SPEED_KEYS]
                    for index, language in enumerate(("en", "zh"))}
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Reviewer Model Benchmark</title>
<meta name="benchmark-version" content="{PAGE_VERSION}">
<meta name="benchmark-scoring-version" content="{SCORING_VERSION}">
<link rel="icon" type="image/svg+xml" href="resources/favicon.svg">
<link rel="stylesheet" href="resources/fonts/fonts.css"><link rel="stylesheet" href="resources/site.css"></head><body><div class="app-shell">
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
<section class="hero" id="overview">{phrase('eyebrow', 'div', 'eyebrow')}{phrase('headline', 'h1')}{phrase('lead', 'p', 'lead')}<div class="version-note">{phrase('version_title', 'strong')} {phrase('version_summary')} {phrase('version_readme')} {readme_link}.</div><div class="summary-strip"><div class="summary-item">{icon('models', 'summary-mark')}<strong>{model_count}</strong>{phrase('stat_models')}</div><div class="summary-item">{icon('configurations', 'summary-mark')}<strong>{len(records)}</strong>{phrase('stat_configurations')}</div><div class="summary-item">{icon('benchmark', 'summary-mark')}<strong>{len(REVIEWERS)}</strong>{phrase('stat_benchmarks')}</div><div class="summary-item">{icon('benchmark', 'summary-mark')}<strong>{run_count}</strong>{phrase('stat_runs')}</div></div></section>
<section class="chart-section" id="score"><div class="section-heading">{phrase('score_kicker', 'div', 'section-kicker')}{phrase('score_title', 'h2')}{phrase('score_desc', 'p')}<p class="section-context">{phrase('score_context')} {phrase('score_models')} {phrase('readme_more')} {readme_link}.</p></div>
<article class="panel"><div class="bar-tooltip" id="benchmark-bar-tooltip-effort" hidden></div><div class="bar-viewport"><div class="bar-scroll" style="--groups:{series_count}">{effort_html}</div></div>{reading('score_read')}</article></section>
<section class="chart-section" id="tradeoffs"><div class="section-heading">{phrase('trade_kicker', 'div', 'section-kicker')}{phrase('trade_title', 'h2')}{phrase('trade_intro', 'p')}</div>{''.join(scatter_sections)}</section>
<section class="chart-section" id="reviewers"><div class="section-heading">{phrase('review_kicker', 'div', 'section-kicker')}{phrase('review_title', 'h2')}{phrase('review_desc', 'p')}</div>
<div class="reviewer-guide">{phrase('reviewer_guide_title', 'h3', 'reviewer-guide-heading')}<div class="reviewer-grid">{''.join(reviewer_guide)}</div></div>
<article class="panel" id="review-score"><div class="chart-panel-heading">{phrase('detail_score_title', 'h3')}</div><div class="bar-tooltip" id="benchmark-bar-tooltip-grouped" hidden></div><div class="bar-frame"><div class="bar-axis-overlay" aria-hidden="true" hidden></div><div class="bar-viewport"><div class="bar-scroll" style="--groups:{len(records)}">{grouped_html}</div></div></div>{reading('detail_score_read')}</article>{''.join(detail_panels)}</section>
<section class="method-section" id="method"><div class="section-heading">{phrase('method_kicker', 'div', 'section-kicker')}{phrase('method_title', 'h2')}</div><div class="panel">{phrase('method_selection', 'p')}{phrase('method_score', 'p')}{phrase('method_runtime', 'p')}{phrase('method_cost', 'p', 'cost-note')}{phrase('method_missing', 'p')}<div class="source-links">{source_links}</div></div></section>
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_json", nargs="?", type=Path,
                        default=Path(__file__).with_name("benchmark-results.json"))
    parser.add_argument("output", nargs="?", type=Path,
                        default=Path(__file__).with_name("charts.html"))
    args = parser.parse_args()
    args.output.write_text(page(json.loads(args.results_json.read_text(encoding="utf-8")),
                                load_pricing()), encoding="utf-8")
    favicon_path = args.output.parent / "resources" / "favicon.svg"
    if favicon_path.parent.is_dir():  # the default output has resources/; elsewhere it is not created
        favicon_path.write_text(favicon_svg(), encoding="utf-8")
    print(args.output)
