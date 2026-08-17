## 语言要求
1. 所有注释、Markdown 和项目提示词必须使用中文。

## 构建要求
1. 只使用 Docker 构建，不得使用本机的 `npm`、Vite 或 Python 重新构建。

## 测试要求
1. 不得自行编写测试用例。
2. 不得运行耗费token且用时超过3分钟的额外测试。

## tools和capabilities
1. `tools/` 和 `capabilities` 下每个工具模块统一使用 `_constants.py`、`_errors.py`、`_schema.py` + 功能文件的结构。
2. 新增或修改功能时，必须同步检查 `_schema.py`、`_errors.py`、`_constants.py` 是否需要更新。
3. Schema 要与真实输入输出保持一致，错误信息必须具体、可理解，并尽量告诉 Agent 应该如何修正。
4. 遇到需求优先看能不能 `tools/` 和 `capabilities` ，修改 `tools/` 和 `capabilities`，或者新增`tools/` 和 `capabilities` 需要和用户汇报后再修改。

## 兼容性
1. 兼容旧数据、备份旧数据时需要和用户确认是否需要备份