import os
from pathlib import Path
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import plotly.utils
from flask import Flask, render_template, request, jsonify
import sys
import warnings
import datetime
warnings.filterwarnings('ignore')

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from model import Kronos, KronosTokenizer, KronosPredictor
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False
    print("Warning: Kronos model cannot be imported, will use simulated data for demonstration")

app = Flask(__name__)

# Global variables to store models
tokenizer = None
model = None
predictor = None

# Available model configurations
AVAILABLE_MODELS = {
    'kronos-mini': {
        'name': 'Kronos-mini',
        'model_id': 'NeoQuasar/Kronos-mini',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-2k',
        'context_length': 2048,
        'params': '4.1M',
        'description': '轻量模型，适合快速预测'
    },
    'kronos-small': {
        'name': 'Kronos-small',
        'model_id': 'NeoQuasar/Kronos-small',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '24.7M',
        'description': '小型模型，兼顾效果与速度'
    },
    'kronos-base': {
        'name': 'Kronos-base',
        'model_id': 'NeoQuasar/Kronos-base',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '102.3M',
        'description': '基础模型，参数更多，计算量更大'
    }
}

def load_data_files():
    """Scan data directory and return available data files"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    data_files = []

    if os.path.exists(data_dir):
        for file in os.listdir(data_dir):
            if file.endswith(('.csv', '.feather')):
                file_path = os.path.join(data_dir, file)
                file_size = os.path.getsize(file_path)
                data_files.append({
                    'name': file,
                    'path': file_path,
                    'size': f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
                })

    return sorted(data_files, key=lambda item: item["name"])

def load_data_file(file_path):
    """Load data file"""
    try:
        data_root = Path(__file__).resolve().parents[1] / 'data'
        resolved = Path(file_path).resolve()
        if not resolved.is_relative_to(data_root.resolve()) or not resolved.is_file():
            return None, '只能读取 data 文件夹中的数据文件'
        file_path = str(resolved)
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.feather'):
            df = pd.read_feather(file_path)
        else:
            return None, "不支持的文件格式"

        # Check required columns
        required_cols = ['open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            return None, f"缺少必需字段： {required_cols}"

        # Process timestamp column
        if 'timestamps' in df.columns:
            df['timestamps'] = pd.to_datetime(df['timestamps'])
        elif 'timestamp' in df.columns:
            df['timestamps'] = pd.to_datetime(df['timestamp'])
        elif 'date' in df.columns:
            # If column name is 'date', rename it to 'timestamps'
            df['timestamps'] = pd.to_datetime(df['date'])
        else:
            # If no timestamp column exists, create one
            return None, '缺少时间字段，请提供 timestamps、timestamp 或 date'

        # Ensure numeric columns are numeric type
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Process volume column (optional)
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        # Process amount column (optional, but not used for prediction)
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

        # Remove rows containing NaN values
        df = df.dropna()

        return df, None

    except Exception as e:
        return None, f"读取文件失败： {str(e)}"

def save_prediction_results(file_path, prediction_type, prediction_results, actual_data, input_data, prediction_params):
    """Save prediction results to file"""
    try:
        # Create prediction results directory
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prediction_results')
        os.makedirs(results_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'prediction_{timestamp}.json'
        filepath = os.path.join(results_dir, filename)

        # Prepare data for saving
        save_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'file_path': file_path,
            'prediction_type': prediction_type,
            'prediction_params': prediction_params,
            'input_data_summary': {
                'rows': len(input_data),
                'columns': list(input_data.columns),
                'price_range': {
                    'open': {'min': float(input_data['open'].min()), 'max': float(input_data['open'].max())},
                    'high': {'min': float(input_data['high'].min()), 'max': float(input_data['high'].max())},
                    'low': {'min': float(input_data['low'].min()), 'max': float(input_data['low'].max())},
                    'close': {'min': float(input_data['close'].min()), 'max': float(input_data['close'].max())}
                },
                'last_values': {
                    'open': float(input_data['open'].iloc[-1]),
                    'high': float(input_data['high'].iloc[-1]),
                    'low': float(input_data['low'].iloc[-1]),
                    'close': float(input_data['close'].iloc[-1])
                }
            },
            'prediction_results': prediction_results,
            'actual_data': actual_data,
            'analysis': {}
        }

        # If actual data exists, perform comparison analysis
        if actual_data and len(actual_data) > 0:
            # Calculate continuity analysis
            if len(prediction_results) > 0 and len(actual_data) > 0:
                last_pred = prediction_results[0]  # First prediction point
            first_actual = actual_data[0]      # First actual point

            save_data['analysis']['continuity'] = {
                    'last_prediction': {
                        'open': last_pred['open'],
                        'high': last_pred['high'],
                        'low': last_pred['low'],
                        'close': last_pred['close']
                    },
                    'first_actual': {
                        'open': first_actual['open'],
                        'high': first_actual['high'],
                        'low': first_actual['low'],
                        'close': first_actual['close']
                    },
                    'gaps': {
                        'open_gap': abs(last_pred['open'] - first_actual['open']),
                        'high_gap': abs(last_pred['high'] - first_actual['high']),
                        'low_gap': abs(last_pred['low'] - first_actual['low']),
                        'close_gap': abs(last_pred['close'] - first_actual['close'])
                    },
                    'gap_percentages': {
                        'open_gap_pct': (abs(last_pred['open'] - first_actual['open']) / first_actual['open']) * 100,
                        'high_gap_pct': (abs(last_pred['high'] - first_actual['high']) / first_actual['high']) * 100,
                        'low_gap_pct': (abs(last_pred['low'] - first_actual['low']) / first_actual['low']) * 100,
                        'close_gap_pct': (abs(last_pred['close'] - first_actual['close']) / first_actual['close']) * 100
                    }
                }

        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

        print(f"Prediction results saved to: {filepath}")
        return filepath

    except Exception as e:
        print(f"Failed to save prediction results: {e}")
        return None

from webui.trading_calendar import resolve_calendar, permitted, calendar_note


def future_timestamps(history, count, calendar="none"):
    """Infer weekly bar slots from recent observations, without inventing holiday data."""
    stamps = pd.Series(pd.to_datetime(history)).sort_values().drop_duplicates()
    if len(stamps) < 2:
        raise ValueError('至少需要两条不同时间的历史数据')
    recent = stamps[stamps >= stamps.iloc[-1] - pd.Timedelta(days=60)]
    slots = {}
    for weekday in range(7):
        subset = recent[recent.dt.weekday == weekday]
        if subset.empty:
            continue
        days = subset.dt.normalize().nunique()
        counts = subset.dt.strftime('%H:%M:%S').value_counts()
        slots[weekday] = sorted(counts[counts >= max(1, days * 0.5)].index)
    daily = recent.dt.normalize().nunique() == len(recent) and stamps.diff().dropna().median() >= pd.Timedelta(hours=18)
    # Exchange calendar determines weekdays; reuse observed bar-label slots across days.
    common_slots = sorted({slot for values in slots.values() for slot in values})
    if daily:
        common_slots = [recent.dt.strftime('%H:%M:%S').mode().iloc[0]]
    last = stamps.iloc[-1]
    result = []
    for offset in range(3660):
        day = last.normalize() + pd.Timedelta(days=offset)
        for slot in (common_slots if calendar != 'none' else slots.get(day.weekday(), [])):
            stamp = day + pd.Timedelta(slot)
            if stamp > last and (calendar == "none" or permitted(stamp, daily)):
                result.append(stamp)
                if len(result) == count:
                    return pd.Series(result)
    raise ValueError('无法从历史数据推断未来交易时段')


def create_prediction_chart(history, pred_df):
    """Use equal-width categories and the exact timestamps passed to the model."""
    fig = go.Figure()
    labels = []
    has_volume = 'volume' in history.columns
    for frame, times, name, up, down in [
        (history, history['timestamps'], f'历史 K 线（{len(history)} 根）', '#26A69A', '#EF5350'),
        (pred_df, pred_df.index, f'未来预测（{len(pred_df)} 根）', '#3B82F6', '#A855F7')
    ]:
        x = [pd.Timestamp(t).strftime('%Y-%m-%d %H:%M:%S') for t in times]
        labels.extend(x)
        fig.add_trace(go.Candlestick(x=x, open=frame['open'], high=frame['high'],
            low=frame['low'], close=frame['close'], name=name,
            increasing_line_color=up, decreasing_line_color=down))
        if has_volume and 'volume' in frame.columns:
            volume = pd.to_numeric(frame['volume'], errors='coerce')
            # Invalid values are gaps, not fabricated zero-volume bars.
            volume = [float(v) if pd.notna(v) and np.isfinite(v) and v >= 0 else None for v in volume]
            colors = [up if close >= opening else down
                      for opening, close in zip(frame['open'], frame['close'])]
            volume_name = '历史成交量' if frame is history else '预测成交量'
            fig.add_trace(go.Bar(x=x, y=volume, yaxis='y2', name=volume_name,
                marker_color=colors, opacity=0.75,
                hovertemplate='%{x}<br>' + volume_name + '：%{y:,.2f}<extra></extra>'))
    tick_step = max(1, len(labels) // 8)
    fig.update_layout(title='最新历史 K 线与未来预测', template='plotly_dark', paper_bgcolor='#101722', plot_bgcolor='#101722',
        font=dict(color='#aebfd6'),
        height=600, yaxis_title='价格', xaxis_title='K 线连续排列（休市空档已折叠）',
        legend=dict(orientation='h'), margin=dict(t=90, b=100))
    fig.update_xaxes(type='category', categoryorder='array', categoryarray=labels,
        rangeslider_visible=False, tickmode='array', tickvals=labels[::tick_step],
        ticktext=[v[:16] for v in labels[::tick_step]], tickangle=-25)
    if has_volume:
        fig.update_layout(
            yaxis=dict(domain=[0.30, 1], title='价格'),
            yaxis2=dict(domain=[0, 0.22], title='成交量', rangemode='tozero', anchor='x'),
            xaxis=dict(anchor='y2'), bargap=0.15)
    fig.add_shape(type='line', xref='x', yref='paper', x0=len(history)-0.5,
        x1=len(history)-0.5, y0=0, y1=1, line=dict(color='#667eea', dash='dash'))
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

from webui import market_data

@app.route('/api/market/catalog')
def market_catalog():
    try:
        return jsonify(market_data.catalog(request.args.get('refresh') == '1'))
    except Exception as e:
        return jsonify(error=f'品种目录获取失败：{e}'), 502

@app.route('/api/market/download', methods=['POST'])
def market_download():
    try:
        data=request.get_json() or {}
        return jsonify(market_data.download(data.get('node'), data.get('period')))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f'行情更新失败：{e}'), 502

@app.route('/api/health')
def health():
    return jsonify(status='ok', model_available=MODEL_AVAILABLE, model_loaded=predictor is not None)


@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/api/data-files')
def get_data_files():
    """Get available data file list"""
    data_files = load_data_files()
    return jsonify(data_files)

@app.route('/api/load-data', methods=['POST'])
def load_data():
    """Load data file"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')

        if not file_path:
            return jsonify({'error': '文件路径不能为空'}), 400

        df, error = load_data_file(file_path)
        if error:
            return jsonify({'error': error}), 400

        # Detect data time frequency
        def detect_timeframe(df):
            if len(df) < 2:
                return "未知"

            time_diffs = df['timestamps'].sort_values().diff().dropna()
            time_diffs = time_diffs[time_diffs > pd.Timedelta(0)]

            if time_diffs.empty:
                return "未知"

            # Use the most common interval so market closures do not inflate it.
            avg_diff = time_diffs.mode().iloc[0]

            # Convert to readable format
            if avg_diff < pd.Timedelta(minutes=1):
                return f"{avg_diff.total_seconds():.0f} 秒"
            elif avg_diff < pd.Timedelta(hours=1):
                return f"{avg_diff.total_seconds() / 60:.0f} 分钟"
            elif avg_diff < pd.Timedelta(days=1):
                return f"{avg_diff.total_seconds() / 3600:.0f} 小时"
            else:
                return f"{avg_diff.days} 天"

        # Return data information
        data_info = {
            'rows': len(df),
            'columns': list(df.columns),
            'start_date': df['timestamps'].min().isoformat() if 'timestamps' in df.columns else 'N/A',
            'end_date': df['timestamps'].max().isoformat() if 'timestamps' in df.columns else 'N/A',
            'price_range': {
                'min': float(df[['open', 'high', 'low', 'close']].min().min()),
                'max': float(df[['open', 'high', 'low', 'close']].max().max())
            },
            'prediction_columns': ['open', 'high', 'low', 'close'] + (['volume'] if 'volume' in df.columns else []),
            'timeframe': market_data.PERIODS.get(market_data.metadata(file_path).get('period'), detect_timeframe(df))
        }

        return jsonify({
            'success': True,
            'data_info': data_info,
            'message': f'数据加载成功，共 {len(df)} 行'
        })

    except Exception as e:
        return jsonify({'error': f'加载数据失败： {str(e)}'}), 500

@app.route('/api/predict', methods=['POST'])
def predict():
    try:
        data = request.get_json() or {}
        file_path = data.get('file_path')
        lookback = int(data.get('lookback', 400))
        pred_len = int(data.get('pred_len', 120))
        temperature = float(data.get('temperature', 1.0))
        top_p = float(data.get('top_p', 0.9))
        sample_count = int(data.get('sample_count', 1))
        if not file_path:
            return jsonify(error='文件路径不能为空'), 400
        if not (2 <= lookback <= 512 and 1 <= pred_len <= 512
                and 0.1 <= temperature <= 2 and 0 < top_p <= 1 and 1 <= sample_count <= 5):
            return jsonify(error='参数超出允许范围'), 400
        df, error = load_data_file(file_path)
        if error:
            return jsonify(error=error), 400
        df = df.sort_values('timestamps').drop_duplicates('timestamps', keep='last').reset_index(drop=True)
        if len(df) < lookback:
            return jsonify(error=f'历史数据不足，需要 {lookback} 条，当前 {len(df)} 条'), 400
        if predictor is None:
            return jsonify(error='请先加载模型'), 400
        if lookback > predictor.max_context:
            return jsonify(error=f'当前模型最多支持 {predictor.max_context} 条历史数据'), 400
        history = df.tail(lookback).reset_index(drop=True)
        meta = market_data.metadata(file_path)
        selection = data.get('calendar', 'auto')
        if selection == 'auto' and meta.get('calendar'):
            selection = meta['calendar']
        calendar = resolve_calendar(selection, file_path)
        period = meta.get('period')
        if period in ('weekly', 'monthly'):
            freq = 'W-FRI' if period == 'weekly' else 'M'
            start = pd.Period(history.timestamps.iloc[-1], freq=freq) + 1
            future = pd.Series(pd.period_range(start, periods=pred_len, freq=freq).end_time.normalize())
        else:
            future = future_timestamps(df['timestamps'], pred_len, calendar)
        cols = [c for c in ['open', 'high', 'low', 'close', 'volume', 'amount'] if c in history]
        pred_df = predictor.predict(df=history[cols], x_timestamp=history['timestamps'],
            y_timestamp=future, pred_len=pred_len, T=temperature, top_p=top_p,
            sample_count=sample_count, verbose=False)
        if not np.isfinite(pred_df.to_numpy()).all():
            raise ValueError('模型返回非有限数值，请重新预测')
        results = [dict(timestamp=pd.Timestamp(t).isoformat(),
                       **{c: float(v) for c, v in row.items()}) for t, row in pred_df.iterrows()]
        note = ('周/月线预测日期为下一周期结束日标签，不代表已核对的具体交易日；当前周期可能尚未收盘。' if period in ('weekly', 'monthly') else calendar_note(calendar))
        prediction_type = f'使用文件末尾 {lookback} 根 K 线，预测其后 {pred_len} 根未来 K 线'
        save_prediction_results(file_path, prediction_type, results, [], history[cols],
            dict(lookback=lookback, pred_len=pred_len, temperature=temperature, top_p=top_p,
                 sample_count=sample_count, mode='future', history_end=history.timestamps.iloc[-1].isoformat(),
                 timestamp_note=note, calendar=calendar))
        return jsonify(success=True, mode='future', prediction_type=prediction_type,
            chart=create_prediction_chart(history, pred_df), prediction_results=results,
            actual_data=[], has_comparison=False, timestamp_note=note, calendar=calendar,
            history_end=history.timestamps.iloc[-1].isoformat(),
            forecast_start=future.iloc[0].isoformat(), forecast_end=future.iloc[-1].isoformat(),
            message=f'预测完成：历史截至 {history.timestamps.iloc[-1]}，已生成其后 {pred_len} 根未来 K 线。')
    except (ValueError, TypeError) as e:
        return jsonify(error=f'预测参数或数据有误：{e}'), 400
    except Exception as e:
        app.logger.exception('Future prediction failed')
        return jsonify(error=f'预测失败：{e}'), 500

@app.route('/api/load-model', methods=['POST'])
def load_model():
    """Load Kronos model"""
    global tokenizer, model, predictor

    try:
        if not MODEL_AVAILABLE:
            return jsonify({'error': 'Kronos 模型库不可用'}), 400

        data = request.get_json()
        model_key = data.get('model_key', 'kronos-small')
        device = data.get('device', 'cpu')

        if model_key not in AVAILABLE_MODELS:
            return jsonify({'error': f'不支持的模型： {model_key}'}), 400

        model_config = AVAILABLE_MODELS[model_key]

        # Load tokenizer and model
        tokenizer = KronosTokenizer.from_pretrained(model_config['tokenizer_id'])
        model = Kronos.from_pretrained(model_config['model_id'])

        # Create predictor
        predictor = KronosPredictor(model, tokenizer, device=device, max_context=model_config['context_length'])

        return jsonify({
            'success': True,
            'message': f'模型加载成功：{model_config["name"]}（{model_config["params"]}），运行设备：{device}',
            'model_info': {
                'name': model_config['name'],
                'params': model_config['params'],
                'context_length': model_config['context_length'],
                'description': model_config['description']
            }
        })

    except Exception as e:
        return jsonify({'error': f'模型加载失败： {str(e)}'}), 500

@app.route('/api/available-models')
def get_available_models():
    """Get available model list"""
    return jsonify({
        'models': AVAILABLE_MODELS,
        'model_available': MODEL_AVAILABLE
    })

@app.route('/api/model-status')
def get_model_status():
    """Get model status"""
    if MODEL_AVAILABLE:
        if predictor is not None:
            return jsonify({
                'available': True,
                'loaded': True,
                'message': 'Kronos 模型已加载，可开始预测',
                'current_model': {
                    'name': predictor.model.__class__.__name__,
                    'device': str(next(predictor.model.parameters()).device)
                }
            })
        else:
            return jsonify({
                'available': True,
                'loaded': False,
                'message': 'Kronos 模型可用，尚未加载'
            })
    else:
        return jsonify({
            'available': False,
            'loaded': False,
            'message': 'Kronos 模型库不可用，请安装相关依赖'
        })

if __name__ == '__main__':
    print("Starting Kronos Web UI...")
    print(f"Model availability: {MODEL_AVAILABLE}")
    if MODEL_AVAILABLE:
        print("Tip: You can load Kronos model through /api/load-model endpoint")
    else:
        print("Tip: Will use simulated data for demonstration")

    app.run(debug=True, host='0.0.0.0', port=7070)
