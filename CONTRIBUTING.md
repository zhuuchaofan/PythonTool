# 🛠️ 开发规范

> 本文档定义了 Python 小工具项目的开发规范和最佳实践。

---

## 1. 📂 目录与命名规范

### 1.1 工具目录结构

每个工具应放在 `tools/` 目录下的独立文件夹中：

```
tools/
└── my_tool/
    ├── README.md       # 工具说明（必须）
    ├── main.py         # 入口文件（必须）
    ├── config.py       # 配置文件（可选）
    └── requirements.txt # 工具专属依赖（可选）
```

### 1.2 命名规范

| 类型        | 规范               | 示例              |
| ----------- | ------------------ | ----------------- |
| 文件夹      | `snake_case`       | `image_converter` |
| Python 文件 | `snake_case`       | `file_handler.py` |
| 类          | `PascalCase`       | `ImageProcessor`  |
| 函数/变量   | `snake_case`       | `process_image()` |
| 常量        | `UPPER_SNAKE_CASE` | `MAX_FILE_SIZE`   |

---

## 2. 🐍 代码风格

### 2.1 基本原则

- **遵循 PEP 8** 代码风格指南
- **每行不超过 88 字符**（Black 格式化工具默认）
- **使用 Type Hints** 进行类型注解
- **编写 Docstring** 解释函数和类

### 2.2 导入顺序

```python
# 1. 标准库
import os
import sys
from pathlib import Path

# 2. 第三方库
import requests
from PIL import Image

# 3. 本地模块
from utils.logger import setup_logger
```

### 2.3 Docstring 格式

使用 Google 风格的 Docstring：

```python
def process_file(file_path: str, encoding: str = "utf-8") -> dict:
    """处理指定文件并返回结果。

    Args:
        file_path: 文件的绝对路径。
        encoding: 文件编码，默认为 utf-8。

    Returns:
        包含处理结果的字典。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
    """
    pass
```

---

## 3. 📝 工具 README 模板

每个工具的 `README.md` 应包含以下内容：

```markdown
# 工具名称

## 📖 简介

简要描述工具的功能和用途。

## 🔧 使用方法

\`\`\`bash
python main.py [参数]
\`\`\`

## ⚙️ 配置说明

描述配置项（如有）。

## 📋 示例

提供使用示例。

## 📦 依赖

列出特殊依赖（如有）。
```

---

## 4. 🔒 安全规范

### 4.1 敏感信息

- ❌ **禁止** 在代码中硬编码密钥、密码、API Token
- ✅ **使用** 环境变量或 `.env` 文件（已加入 `.gitignore`）

```python
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY")
```

### 4.2 文件操作

- 使用 `pathlib.Path` 处理路径
- 操作前检查文件/目录是否存在
- 危险操作（删除、覆盖）前进行确认

---

## 5. 🧪 测试规范

- 对于复杂工具，建议编写单元测试
- 测试文件放在工具目录下的 `tests/` 子目录
- 使用 `pytest` 作为测试框架

---

## 6. 📦 依赖管理

### 6.1 全局依赖

通用依赖添加到根目录 `requirements.txt`

### 6.2 工具专属依赖

特定工具的依赖放在工具目录下的 `requirements.txt`

### 6.3 版本锁定

```
requests==2.31.0
Pillow>=10.0.0,<11.0.0
```

---

## 7. 🏷️ Git 提交规范

### 提交信息格式

```
<type>(<scope>): <subject>

<body>
```

### Type 类型

| Type       | 描述          |
| ---------- | ------------- |
| `feat`     | 新功能/新工具 |
| `fix`      | 修复 Bug      |
| `docs`     | 文档更新      |
| `refactor` | 代码重构      |
| `chore`    | 构建/工具变更 |

### 示例

```
feat(image_converter): 添加图片格式转换工具

- 支持 PNG、JPG、WebP 互转
- 支持批量转换
- 添加质量压缩选项
```
