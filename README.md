📘 智能督学助教系统 - GaussDB 实验项目
项目概述
本项目是一个基于 GaussDB 数据库和大语言模型的智能督学助教系统，旨在帮助学生管理学习进度、查询课程信息、跟踪作业截止日期等。系统通过自然语言处理技术，允许学生使用日常语言提问（如"我有哪些作业没交？"），并自动转换为数据库查询，返回易于理解的回答。

🎯 功能特性
自然语言问答：学生可以用自然语言查询学习相关信息
智能提醒：自动发送邮件提醒即将到期的作业
多维度查询：支持课程安排、作业状态、学习进度等多种查询
个性化建议：根据学生查询历史提供相关建议问题
安全验证：完善的用户验证和 SQL 注入防护
🧰 技术栈
后端：Python + Flask
前端：HTML/CSS/JavaScript
数据库：GaussDB（兼容 PostgreSQL）
AI 模型：OpenAI GPT 或其他兼容大语言模型
定时任务：APScheduler
邮件服务：SMTP
🏗 系统架构
智能督学系统
├── 前端界面 (frontend.html)
│   ├── 用户登录
│   ├── 聊天交互
│   └── 建议问题展示
├── 后端服务 (backend.py)
│   ├── API 路由
│   ├── 用户验证
│   └── 查询处理
├── AI 处理层 (ai_sql_generator.py)
│   ├── 自然语言转 SQL
│   ├── 查询结果格式化
│   └── 对话建议生成
├── 定时任务 (remind_agent.py)
│   └── 作业截止提醒
└── 数据库层 (sql.sql)
    ├── 学生信息
    ├── 课程安排
    └── 作业提交记录
⚙ 快速开始
环境准备
安装 Python 3.8+
安装依赖库：
pip install -r requirements.txt
准备 GaussDB 数据库实例
创建 .env 文件并配置环境变量（参考 .env.example）
🛠 数据库初始化
使用 SQL 脚本初始化数据库：

psql -h [主机] -p [端口] -U [用户名] -d [数据库名] -f sql.sql
🚀 启动服务
启动后端服务：
python backend.py
启动提醒服务（可选）：
python remind_agent.py
启动前端页面：
打开 frontend.html 即可在浏览器中使用系统

📡 API 接口文档
主要接口
POST /api/login：用户登录
POST /api/query：处理自然语言查询
GET /api/suggestions：获取建议问题列表
GET /health：健康检查
请求示例
{
  "question": "我有哪些作业没交？",
  "user_id": "202311081040"
}
响应示例
{
  "success": true,
  "answer": "📋 您的未提交实验报告:

1. 数据定义与修改 (截止日期: 2025-03-17)
2. 多表查询 (截止日期: 2025-03-31)",
  "query_type": "experiment_report",
  "result_count": 2
}
🗃 数据库设计
students - 学生信息
字段名	类型	说明
student_id	主键	学号
email	字符串	邮箱地址
student_name	字符串	姓名
gender	字符串	性别
Intelligent_Supervision - 课程安排
字段名	类型	说明
serial_number	主键	单元编号
course_content	文本	课程内容
online_learning_date	日期	学习日期
report_deadline	日期	报告截止日
unit_number	整数	单元号
unit_test_date	日期	单元测验日
LabReport - 实验报告提交状态
字段名	类型	说明
serial_number	外键	对应课程单元
student_id	外键	学生编号
submitted	布尔值	是否提交
📂 项目结构
.
├── README.md               # 项目说明文档
├── ai_sql_generator.py     # AI 查询处理模块
├── backend.py              # Flask 后端服务
├── frontend.html           # 前端页面
├── remind_agent.py         # 定时提醒服务
├── requirements.txt        # 依赖库列表
└── sql.sql                 # 数据库初始化脚本
✅ 使用示例
登录系统
提问："我有哪些作业没交？"
系统返回未提交作业及截止日期
浏览建议问题获取更多学习信息
⚠ 注意事项
请确保数据库连接参数配置正确
邮件提醒功能需配置可用的 SMTP 服务
生产环境建议使用 HTTPS 与身份认证机制加强安全性
📄 许可证
本项目基于 MIT License 开源发布。
