# Kronos Web

一个本地运行的中文 K 线预测网站，基于 [ShiYu/Kronos](https://github.com/shiyu-coder/Kronos) 开源模型。Python + Flask + Plotly，无需 Node.js 构建。

## 功能

- 中文模型、设备与数据选择；支持 CPU、Apple MPS、CUDA。
- 使用文件末尾最新历史数据预测其后的未来 K 线。
- K 线等距连续排列，折叠休市空白，区分历史与预测。
- 刷新本地数据目录，无需重新加载模型。
- 导出带模型、参数、数据来源文件和时间范围的 PNG。
- 大商所、上期所 2026 年休市及停夜盘日历；跨出覆盖年份时明确报错。
- 配套下载豆一、棕榈油、不锈钢主连的分钟与日线数据。

## 本地启动

使用 **Python 3.12**（依赖基线适配版本）。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/download_data.py --symbol P0 --period 30
python run.py
```

浏览器打开 **http://127.0.0.1:7071**。

Windows：使用 `py -3.12 -m venv .venv` 创建环境，然后运行 `.venv\Scripts\activate`，其余 Python 命令相同。macOS/Linux 完成依赖安装后也可运行 `./start.command`；macOS 可双击该文件。脚本日志写入 `logs/webui.log`。

默认仅监听本机。可用 `PORT=7080 python run.py` 修改端口。停止服务按 `Control+C`。

## 使用步骤

1. 选择 `Kronos-small` 和计算设备，点击“加载模型”。首次使用从 Hugging Face 下载模型及 tokenizer，需联网。
2. 选择数据文件，点击“加载数据”。新增文件后点击“刷新文件列表”。
3. 选择交易日历。当前三种期货文件可自动识别；其他文件需手动选择。
4. 设置历史条数和未来预测条数，点击“开始预测”。small/base 的历史窗口最多为 512 根。
5. 图中虚线右侧为模型生成的未来 K 线。点击“保存当前预测图片”下载 PNG。

日线预测 20 条就是未来 20 根日 K 线。分钟线预测条数按数据文件周期计算。日历当前只覆盖 2026 年，不能把跨年范围当作已确认交易日期。临时停市与品种特殊调整不在此静态日历中。

## 数据

```bash
python scripts/download_data.py --symbol A0 --period 30
python scripts/download_data.py --symbol SS0 --period 30
python scripts/download_data.py --symbol P0 --period daily
```

可选周期：`1`、`5`、`15`、`30`、`60`、`daily`。数据来自新浪公开接口；分钟历史长度由数据源决定，接口可能变化。下载脚本保留来源说明，过滤无效 OHLC 行，不自行复权。请遵守数据提供方的使用条款。第三方行情和模型权重均不随源码分发。

也可把 CSV 或 Feather 放在 `data/`。必需字段为 `timestamps`（或 `timestamp` / `date`）、`open`、`high`、`low`、`close`；可选 `volume`、`amount`。时间使用北京时间且保持一致；缺少时间字段会报错。仅允许加载 `data/` 内的文件。

## 运行与验证

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

测试不下载模型，覆盖休市、周末、节前夜盘、节后恢复、跨午夜和超出日历覆盖范围。真实模型预测需先下载权重。

- `run.py`：启动入口。
- `webui/app.py`：数据和预测 API。
- `webui/templates/index.html`：中文网站。
- `webui/trading_calendar.py`：交易时段过滤。
- `webui/calendars/cn_futures_2026.json`：日历日期、覆盖范围与公告来源。
- `model/`：上游模型实现，预测器初始化切换到 eval 模式。

新年度日历应在核对交易所公告后扩展配置与测试，不能仅修改覆盖年份。已加载模型驻留内存；本网站按单用户本地工具设计，尚未实现账号、配额或多用户任务队列。前端 Plotly 与 Axios 使用 CDN，需联网加载。运行时缓存、日志、行情和预测结果均被 Git 忽略。

## 开源说明

本项目是基于 Kronos 的非官方衍生网站，保留上游版权声明和 MIT 许可证，详见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。模型权重由 Hugging Face 单独提供，应遵循相应模型仓库的许可。模型输出具有随机性，示例不代表已验证的交易策略。

GitHub 仓库用于公开源码；GitHub Pages 不能直接运行 Python/PyTorch 后端。当前交付为可本地运行的网站，未部署公网推理服务。
