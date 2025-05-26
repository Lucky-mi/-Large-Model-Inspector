from typing import Dict, List
import psycopg2
import logging
from datetime import datetime, timedelta
from enum import Enum
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

# Configure logging with file output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_processor.log'),  # Save logs to a file
        logging.StreamHandler()  # Also print logs to console
    ]
)
logger = logging.getLogger(__name__)

# QueryType Enum
class QueryType(Enum):
    LEARNING_SCHEDULE = "learning_schedule"
    UNIT_TEST = "unit_test"
    EXPERIMENT_REPORT = "experiment_report"
    COURSE_INFO = "course_info"
    STUDENT_PROGRESS = "student_progress"
    DEADLINE_WARNING = "deadline_warning"
    COMPLETION_STATS = "completion_stats"
    TEACHER_FEEDBACK = "teacher_feedback"
    LEARNING_ANALYTICS = "learning_analytics"
    PEER_COMPARISON = "peer_comparison"
    RESOURCE_USAGE = "resource_usage"
    GRADE_INQUIRY = "grade_inquiry"
    ANNOUNCEMENT = "announcement"
    STUDY_RECOMMENDATION = "study_recommendation"

class AIQueryProcessor:
    def __init__(self, openai_api_key=None, db_config=None, model="gpt-4o", base_url=None):
        """
        Initialize AI Query Processor
        """
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            logger.error("OPENAI_API_KEY is not set")
            raise ValueError("OPENAI_API_KEY is not set. Please provide it in the .env file or environment variables.")

        self.db_config = db_config or {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'learning_system'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }
        self.model = model
        self.base_url = base_url or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')

        # Validate database connection
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.close()
            logger.info("Database connection validated successfully")
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            raise ValueError(f"Failed to connect to database: {str(e)}")

        # Initialize OpenAI client
        try:
            self.client = OpenAI(
                api_key=self.openai_api_key,
                base_url=self.base_url
            )
            # Test OpenAI API connectivity (optional, depending on use case)
            self.client.models.list()  # Simple API call to verify key and endpoint
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"OpenAI client initialization failed: {str(e)}")
            raise ValueError(f"Failed to initialize OpenAI client: {str(e)}")

        self.intent_patterns = {
            QueryType.EXPERIMENT_REPORT: ['作业', '实验报告', '未提交', '截止', '逾期'],
            QueryType.GRADE_INQUIRY: ['成绩', '分数', '评分', '得分'],
            QueryType.STUDENT_PROGRESS: ['进度', '完成情况', '学习状况'],
            QueryType.TEACHER_FEEDBACK: ['老师', '反馈', '评价', '建议'],
            QueryType.LEARNING_SCHEDULE: ['安排', '计划', '时间表', '日程'],
            # Removed QueryType.GENERAL_CHAT and QueryType.MOTIVATION as they are not in QueryType Enum
        }
        self.intent_keywords = self._init_intent_keywords()
        logger.info("AIQueryProcessor initialized successfully")

    def _init_intent_keywords(self):
        """Initialize intent recognition keywords"""
        return {
            QueryType.EXPERIMENT_REPORT: [
                "作业", "实验报告", "未提交", "没交", "逾期", "截止", "deadline", "report", "assignment", "homework", "补交"
            ],
            QueryType.UNIT_TEST: [
                "测试", "考试", "单元测试", "unit test", "exam", "quiz", "考核", "测验", "考试安排"
            ],
            QueryType.LEARNING_SCHEDULE: [
                "学习安排", "课程安排", "时间表", "schedule", "计划", "日程", "这周", "下周", "最近", "什么时候学"
            ],
            QueryType.COURSE_INFO: [
                "课程内容", "学习内容", "课程详情", "course", "内容", "学什么", "涵盖", "包含", "课程介绍"
            ],
            QueryType.STUDENT_PROGRESS: [
                "进度", "完成情况", "统计", "progress", "完成率", "学习状况", "表现", "整体情况"
            ],
            QueryType.DEADLINE_WARNING: [
                "即将到期", "快到期", "紧急", "提醒", "警告", "urgent", "soon", "approaching", "催促"
            ],
            QueryType.TEACHER_FEEDBACK: [
                "老师", "教师", "反馈", "评价", "建议", "feedback", "评语", "意见", "指导"
            ],
            QueryType.LEARNING_ANALYTICS: [
                "学习时长", "访问记录", "学习行为", "活跃度", "学习习惯", "analytics", "统计分析"
            ],
            QueryType.PEER_COMPARISON: [
                "同学", "其他人", "排名", "比较", "平均", "对比", "相比", "comparison", "排行"
            ],
            QueryType.RESOURCE_USAGE: [
                "资源", "视频", "课件", "资料", "下载", "观看", "学习资源", "材料"
            ],
            QueryType.GRADE_INQUIRY: [
                "成绩", "分数", "评分", "grade", "score", "多少分", "得分"
            ],
            QueryType.ANNOUNCEMENT: [
                "通知", "公告", "消息", "announcement", "新闻", "最新", "重要通知"
            ],
            QueryType.STUDY_RECOMMENDATION: [
                "建议", "推荐", "应该", "怎么学", "如何", "学习方法", "复习", "准备"
            ]
        }

    def _classify_query_intent(self, question):
        """Classify query intent using keywords"""
        question_lower = question.lower()
        scores = {}

        for query_type, keywords in self.intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword.lower() in question_lower)
            if score > 0:
                scores[query_type] = score

        return max(scores.items(), key=lambda x: x[1])[0] if scores else None




    def process_question(self, question, user_id):
        """
        处理自然语言问题，生成 SQL 并查询数据库
        """
        try:
            # 预分析查询意图
            predicted_intent = self._classify_query_intent(question)

            # 使用大模型生成 SQL
            query_type, sql, params = self._generate_sql(question, user_id, predicted_intent)
            if not sql:
                return {
                    'success': False,
                    'error': '抱歉，我无法理解您的问题。请尝试使用更具体的表达方式，比如"我有哪些作业没交？"、"我的成绩怎么样？"或"老师有什么反馈？"',
                    'query_type': None,
                    'result_count': 0,
                    'suggestions': self._get_general_suggestions()
                }

            # 执行查询
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            results = cursor.fetchall()
            cursor.close()
            conn.close()

            # 格式化答案
            answer = self._format_answer(query_type, results, question, user_id)
            result_count = len(results)

            return {
                'success': True,
                'answer': answer,
                'query_type': query_type.value if query_type else None,
                'sql': sql,
                'results': results,
                'result_count': result_count,
                'suggestions': self.get_conversation_suggestions(query_type) if query_type else []
            }

        except Exception as e:
            logger.error(f"处理查询失败: {str(e)}")
            return {
                'success': False,
                'error': f'查询过程中遇到了技术问题，请稍后重试。如果问题持续存在，请联系系统管理员。',
                'query_type': None,
                'sql': sql if 'sql' in locals() else None,
                'result_count': 0
            }

    def _generate_sql(self, question, user_id, predicted_intent=None):
        """
        使用大模型生成 SQL 查询 - 更详细的数据库结构和示例
        """
        # 详细的数据库表结构和关系说明
        schema = """
        完整数据库表结构:

        1. students (学生信息表)
           - student_id VARCHAR(12) PRIMARY KEY - 学生ID
           - email VARCHAR(50) NOT NULL - 邮箱
           - student_name VARCHAR(50) - 学生姓名
           - gender CHAR(1) - 性别

        2. Intelligent_Supervision (智能督学表)
           - serial_number INT PRIMARY KEY - 序号
           - course_content VARCHAR(50) NOT NULL - 课程内容
           - online_learning_date DATE NOT NULL - 在线学习日期
           - report_deadline DATE NOT NULL - 报告截止日期
           - unit_number INT NOT NULL - 单元号
           - unit_test_date DATE NOT NULL - 单元测试日期

        3. LabReport (实验报告表)
           - serial_number INT - 序号 (外键引用 Intelligent_Supervision.serial_number)
           - student_id VARCHAR(12) - 学生ID (外键引用 students.student_id)
           - submitted BOOLEAN DEFAULT false - 是否已提交
           - 主键: (serial_number, student_id)

        4. StudentGrades (学生成绩表)
           - grade_id SERIAL PRIMARY KEY - 成绩ID
           - student_id VARCHAR(12) - 学生ID (外键)
           - serial_number INT - 序号 (外键)
           - grade DECIMAL(5,2) - 成绩 (0-100)
           - submit_date DATE - 实际提交日期
           - late_days INT DEFAULT 0 - 迟交天数
           - comments TEXT - 教师评语
           - created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        5. LearningActivity (学习行为记录表)
           - activity_id SERIAL PRIMARY KEY - 活动ID
           - student_id VARCHAR(12) - 学生ID (外键)
           - serial_number INT - 序号 (外键)
           - activity_type VARCHAR(20) - 活动类型 ('view', 'download', 'submit', 'review')
           - activity_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP - 活动时间
           - duration_minutes INT - 学习时长(分钟)
           - device_type VARCHAR(20) - 设备类型 ('PC', 'Mobile', 'Tablet')
           - ip_address VARCHAR(15) - IP地址

        6. Announcements (通知公告表)
           - announcement_id SERIAL PRIMARY KEY - 公告ID
           - title VARCHAR(100) NOT NULL - 标题
           - content TEXT NOT NULL - 内容
           - announcement_type VARCHAR(20) - 公告类型 ('deadline', 'exam', 'general', 'urgent')
           - target_students TEXT - 目标学生ID (JSON格式，null表示全体)
           - publish_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP - 发布时间
           - expire_date DATE - 过期日期
           - is_active BOOLEAN DEFAULT TRUE - 是否激活
           - created_by VARCHAR(50) DEFAULT 'system' - 创建者

        7. TeacherFeedback (教师反馈表)
           - feedback_id SERIAL PRIMARY KEY - 反馈ID
           - student_id VARCHAR(12) - 学生ID (外键)
           - serial_number INT - 序号 (外键)
           - feedback_type VARCHAR(20) - 反馈类型 ('praise', 'reminder', 'warning', 'suggestion')
           - feedback_content TEXT NOT NULL - 反馈内容
           - feedback_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP - 反馈时间
           - is_read BOOLEAN DEFAULT FALSE - 是否已读
           - teacher_name VARCHAR(50) DEFAULT '系统教师' - 教师姓名

        8. ResourceAccess (学习资源访问记录表)
           - access_id SERIAL PRIMARY KEY - 访问ID
           - student_id VARCHAR(12) - 学生ID (外键)
           - serial_number INT - 序号 (外键)
           - resource_type VARCHAR(30) - 资源类型 ('lecture_video', 'slides', 'example_code', 'reference')
           - resource_name VARCHAR(100) - 资源名称
           - access_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP - 访问时间
           - access_duration_seconds INT - 访问时长(秒)

        9. 统计视图:
           - StudentProgressView - 学生进度统计视图
           - CourseCompletionView - 课程完成情况统计视图

        表关系:
        - LabReport 通过 serial_number 关联 Intelligent_Supervision
        - LabReport 通过 student_id 关联 students
        - StudentGrades 关联 students 和 Intelligent_Supervision
        - LearningActivity 记录学生的学习行为轨迹
        - TeacherFeedback 存储教师对学生的个性化反馈
        - ResourceAccess 追踪学生对学习资源的使用情况
        """

        # 构建更专业的提示词
        intent_hint = f"\n预测查询意图: {predicted_intent.value if predicted_intent else '未知'}" if predicted_intent else ""

        prompt = f"""
        你是一个专业的SQL查询生成助手，专门为智能督学系统服务。请根据学生的自然语言问题生成安全、准确的SQL查询。

        {schema}

        当前用户: 学生ID '{user_id}'
        用户问题: "{question}"{intent_hint}

        请遵循以下规则:
        1. 所有查询必须使用参数化查询 (%s) 防止SQL注入
        2. 涉及学生个人数据时，必须添加 student_id = %s 条件限制
        3. 日期比较使用 CURRENT_DATE 获取当前日期
        4. 优先查询最相关和最有用的信息
        5. 对于模糊问题，选择最可能的解释
        6. 利用新增的表结构提供更丰富的查询结果

        输出格式 (严格的JSON):
        ```json
        {{
            "query_type": "learning_schedule|unit_test|experiment_report|course_info|student_progress|deadline_warning|completion_stats|teacher_feedback|learning_analytics|peer_comparison|resource_usage|grade_inquiry|announcement|study_recommendation",
            "sql": "完整的SQL查询语句",
            "params": ["参数列表"],
            "explanation": "查询意图的简短说明"
        }}
        ```

        增强查询示例:

        问题: "我有哪些作业没交？" / "未提交的实验报告"
        ```json
        {{
            "query_type": "experiment_report",
            "sql": "SELECT ins.serial_number, ins.course_content, ins.report_deadline, CASE WHEN ins.report_deadline < CURRENT_DATE THEN '已逾期' ELSE '未逾期' END as status, CASE WHEN ins.report_deadline - CURRENT_DATE <= 3 THEN '紧急' WHEN ins.report_deadline - CURRENT_DATE <= 7 THEN '即将到期' ELSE '正常' END as urgency FROM Intelligent_Supervision ins LEFT JOIN LabReport lr ON ins.serial_number = lr.serial_number AND lr.student_id = %s WHERE lr.submitted IS FALSE OR lr.submitted IS NULL ORDER BY ins.report_deadline",
            "params": ["{user_id}"],
            "explanation": "查询学生未提交的实验报告及其紧急程度"
        }}
        ```

        问题: "我的成绩怎么样？" / "我得了多少分？"
        ```json
        {{
            "query_type": "grade_inquiry",
            "sql": "SELECT ins.course_content, sg.grade, sg.submit_date, sg.late_days, sg.comments, CASE WHEN sg.grade >= 90 THEN '优秀' WHEN sg.grade >= 80 THEN '良好' WHEN sg.grade >= 70 THEN '中等' WHEN sg.grade >= 60 THEN '及格' ELSE '不及格' END as grade_level FROM StudentGrades sg JOIN Intelligent_Supervision ins ON sg.serial_number = ins.serial_number WHERE sg.student_id = %s ORDER BY sg.submit_date DESC",
            "params": ["{user_id}"],
            "explanation": "查询学生的成绩记录和等级评价"
        }}
        ```

        问题: "老师对我有什么反馈？" / "教师评价"
        ```json
        {{
            "query_type": "teacher_feedback",
            "sql": "SELECT tf.feedback_type, tf.feedback_content, tf.feedback_date, tf.teacher_name, ins.course_content, CASE WHEN tf.feedback_type = 'praise' THEN '表扬' WHEN tf.feedback_type = 'reminder' THEN '提醒' WHEN tf.feedback_type = 'warning' THEN '警告' WHEN tf.feedback_type = 'suggestion' THEN '建议' ELSE '其他' END as feedback_type_zh FROM TeacherFeedback tf LEFT JOIN Intelligent_Supervision ins ON tf.serial_number = ins.serial_number WHERE tf.student_id = %s ORDER BY tf.feedback_date DESC LIMIT 10",
            "params": ["{user_id}"],
            "explanation": "查询教师对学生的最新反馈信息"
        }}
        ```

        问题: "我的学习时间统计" / "学习行为分析"
        ```json
        {{
            "query_type": "learning_analytics",
            "sql": "SELECT ins.course_content, COUNT(la.activity_id) as total_activities, SUM(la.duration_minutes) as total_minutes, AVG(la.duration_minutes) as avg_duration, la.device_type, COUNT(DISTINCT DATE(la.activity_date)) as active_days FROM LearningActivity la JOIN Intelligent_Supervision ins ON la.serial_number = ins.serial_number WHERE la.student_id = %s GROUP BY ins.course_content, la.device_type ORDER BY total_minutes DESC",
            "params": ["{user_id}"],
            "explanation": "分析学生的学习行为和时间分布"
        }}
        ```

        问题: "我和其他同学相比怎么样？" / "班级排名"
        ```json
        {{
            "query_type": "peer_comparison",
            "sql": "WITH student_stats AS (SELECT s.student_id, s.student_name, COUNT(CASE WHEN lr.submitted = TRUE THEN 1 END) as completed, AVG(sg.grade) as avg_grade FROM students s LEFT JOIN LabReport lr ON s.student_id = lr.student_id LEFT JOIN StudentGrades sg ON s.student_id = sg.student_id GROUP BY s.student_id, s.student_name), ranked_students AS (SELECT *, RANK() OVER (ORDER BY completed DESC, avg_grade DESC) as rank FROM student_stats) SELECT rs.rank, rs.completed, rs.avg_grade, (SELECT COUNT(*) FROM ranked_students) as total_students FROM ranked_students rs WHERE rs.student_id = %s",
            "params": ["{user_id}"],
            "explanation": "比较当前学生与同班同学的学习表现"
        }}
        ```

        问题: "有什么重要通知？" / "最新公告"
        ```json
        {{
            "query_type": "announcement",
            "sql": "SELECT title, content, announcement_type, publish_date, expire_date, CASE WHEN announcement_type = 'urgent' THEN '紧急' WHEN announcement_type = 'deadline' THEN '截止提醒' WHEN announcement_type = 'exam' THEN '考试通知' ELSE '一般通知' END as type_zh FROM Announcements WHERE is_active = TRUE AND (target_students IS NULL OR target_students::text LIKE %s) AND (expire_date IS NULL OR expire_date >= CURRENT_DATE) ORDER BY CASE WHEN announcement_type = 'urgent' THEN 1 ELSE 2 END, publish_date DESC LIMIT 5",
            "params": [f'%"{user_id}"%'],
            "explanation": "查询针对该学生的有效通知公告"
        }}
        ```

        问题: "我应该重点学习什么？" / "学习建议"
        ```json
        {{
            "query_type": "study_recommendation",
            "sql": "SELECT ins.course_content, ins.online_learning_date, ins.report_deadline, CASE WHEN lr.submitted IS FALSE OR lr.submitted IS NULL THEN '需要完成实验报告' END as recommendation, CASE WHEN ins.report_deadline - CURRENT_DATE <= 7 THEN '高优先级' WHEN ins.report_deadline - CURRENT_DATE <= 14 THEN '中优先级' ELSE '低优先级' END as priority FROM Intelligent_Supervision ins LEFT JOIN LabReport lr ON ins.serial_number = lr.serial_number AND lr.student_id = %s WHERE lr.submitted IS FALSE OR lr.submitted IS NULL ORDER BY ins.report_deadline",
            "params": ["{user_id}"],
            "explanation": "基于截止日期和完成情况给出学习建议"
        }}
        ```

        问题: "我看了多少学习资料？" / "资源使用情况"
        ```json
        {{
            "query_type": "resource_usage",
            "sql": "SELECT ra.resource_type, ra.resource_name, COUNT(*) as access_count, SUM(ra.access_duration_seconds) as total_seconds, AVG(ra.access_duration_seconds) as avg_seconds, MAX(ra.access_date) as last_access, CASE WHEN ra.resource_type = 'lecture_video' THEN '讲课视频' WHEN ra.resource_type = 'slides' THEN '课件' WHEN ra.resource_type = 'example_code' THEN '示例代码' WHEN ra.resource_type = 'reference' THEN '参考资料' ELSE '其他' END as resource_type_zh FROM ResourceAccess ra WHERE ra.student_id = %s GROUP BY ra.resource_type, ra.resource_name ORDER BY total_seconds DESC",
            "params": ["{user_id}"],
            "explanation": "统计学生对各类学习资源的使用情况"
        }}
        ```

        请根据用户问题生成最合适的SQL查询，充分利用数据库中的丰富信息。
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": "你是一个专业的SQL生成助手，专门为教育督学系统服务。请严格按照JSON格式输出，确保SQL查询的安全性和准确性。充分利用数据库中的所有表结构，提供详细和有用的查询结果。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1  # 降低随机性，提高一致性
            )

            result = json.loads(response.choices[0].message.content)

            query_type = QueryType(result['query_type']) if result.get('query_type') in [qt.value for qt in
                                                                                         QueryType] else None
            sql = result.get('sql', '').strip()
            params = result.get('params', [])

            # 增强的SQL安全性验证
            if not sql or not self._validate_sql_safety(sql):
                logger.warning("生成的SQL不安全或无效")
                return None, None, None

            logger.info(f"生成SQL成功: {result.get('explanation', '无说明')}")
            return query_type, sql, params

        except Exception as e:
            logger.error(f"生成 SQL 失败: {str(e)}")
            return None, None, None

    def _validate_sql_safety(self, sql):
        """增强的SQL安全性验证"""
        if not sql:
            return False

        sql_upper = sql.upper()

        # 危险操作检查
        dangerous_operations = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
        if any(op in sql_upper for op in dangerous_operations):
            return False

        # 确保是SELECT查询
        if not sql_upper.strip().startswith('SELECT') and not sql_upper.strip().startswith('WITH'):
            return False

        return True

    def _format_answer(self, query_type, results, question, user_id):
        """
        将查询结果格式化为更专业的自然语言答案 - 支持所有新的查询类型
        """
        if not results:
            return self._format_empty_result(query_type, question)

        current_date = datetime.now().date()

        formatters = {
            QueryType.EXPERIMENT_REPORT: self._format_experiment_report_answer,
            QueryType.UNIT_TEST: self._format_unit_test_answer,
            QueryType.COURSE_INFO: self._format_course_info_answer,
            QueryType.STUDENT_PROGRESS: self._format_student_progress_answer,
            QueryType.LEARNING_SCHEDULE: self._format_learning_schedule_answer,
            QueryType.DEADLINE_WARNING: self._format_deadline_warning_answer,
            QueryType.TEACHER_FEEDBACK: self._format_teacher_feedback_answer,
            QueryType.PEER_COMPARISON: self._format_peer_comparison_answer,
            QueryType.RESOURCE_USAGE: self._format_resource_usage_answer,
            QueryType.GRADE_INQUIRY: self._format_grade_inquiry_answer,
            QueryType.ANNOUNCEMENT: self._format_announcement_answer,
            QueryType.STUDY_RECOMMENDATION: self._format_study_recommendation_answer
        }

        formatter = formatters.get(query_type, self._format_default_answer)

        if query_type in [QueryType.LEARNING_SCHEDULE, QueryType.DEADLINE_WARNING, QueryType.LEARNING_ANALYTICS]:
            return formatter(results, current_date)
        else:
            return formatter(results)

    def _format_teacher_feedback_answer(self, results):
        """格式化教师反馈查询结果"""
        if not results:
            return "📝 暂时没有收到老师的反馈，请继续努力学习！"

        answer = "👨‍🏫 **教师反馈信息:**\n\n"

        for row in results:
            if len(row) >= 6:
                feedback_type, content, date, teacher, course, type_zh = row[:6]

                # 选择合适的表情符号
                emoji_map = {
                    '表扬': '🌟',
                    '提醒': '⏰',
                    '警告': '⚠️',
                    '建议': '💡'
                }
                emoji = emoji_map.get(type_zh, '📝')

                answer += f"{emoji} **{type_zh}** - {teacher}\n"
                answer += f"📚 课程: {course or '通用'}\n"
                answer += f"💬 内容: {content}\n"
                answer += f"📅 时间: {date.strftime('%Y-%m-%d %H:%M') if hasattr(date, 'strftime') else date}\n\n"

        answer += "💡 **建议**: 请认真对待老师的反馈，这将有助于您的学习进步！"
        return answer

    def _format_experiment_report_answer(self, results):
        """格式化实验报告查询结果"""
        if not results:
            return "📋 您目前没有未提交的实验报告，继续保持！"

        answer = "📋 **未提交的实验报告:**\n\n"

        for row in results:
            if len(row) >= 5:
                serial_number, course_content, report_deadline, status, urgency = row[:5]

                emoji_map = {
                    '紧急': '🚨',
                    '即将到期': '⏰',
                    '正常': '✅'
                }
                emoji = emoji_map.get(urgency, '📝')

                answer += f"{emoji} **{course_content}** (序号: {serial_number})\n"
                answer += f"   📅 截止日期: {report_deadline.strftime('%Y-%m-%d') if hasattr(report_deadline, 'strftime') else report_deadline}\n"
                answer += f"   📊 状态: {status}\n"
                answer += f"   ⚠️ 紧急程度: {urgency}\n\n"

        answer += "💡 **建议**: 请优先完成紧急和即将到期的实验报告，避免逾期影响成绩！"
        return answer

    def _format_unit_test_answer(self, results):
        """格式化单元测试查询结果"""
        if not results:
            return "📝 暂无即将进行的单元测试信息。"

        answer = "📝 **单元测试安排:**\n\n"

        for row in results:
            if len(row) >= 3:
                course_content, unit_number, test_date = row[:3]

                answer += f"📚 **{course_content}** (单元: {unit_number})\n"
                answer += f"   📅 测试日期: {test_date.strftime('%Y-%m-%d') if hasattr(test_date, 'strftime') else test_date}\n\n"

        answer += "💡 **建议**: 请提前复习相关课程内容，确保测试顺利通过！"
        return answer

    def _format_course_info_answer(self, results):
        """格式化课程信息查询结果"""
        if not results:
            return "📚 暂无课程信息。"

        answer = "📚 **课程信息:**\n\n"

        for row in results:
            if len(row) >= 2:
                course_content, unit_number = row[:2]

                answer += f"📖 **{course_content}** (单元: {unit_number})\n\n"

        answer += "💡 **建议**: 请查看课程资源，合理安排学习时间！"
        return answer

    def _format_student_progress_answer(self, results):
        """格式化学生进度查询结果"""
        if not results:
            return "📈 暂无学习进度数据。"

        answer = "📈 **您的学习进度:**\n\n"

        for row in results:
            if len(row) >= 3:
                course_content, completed, total = row[:3]
                completion_rate = (completed / total * 100) if total > 0 else 0

                answer += f"📚 **{course_content}**\n"
                answer += f"   ✅ 已完成: {completed}/{total}\n"
                answer += f"   📊 完成率: {completion_rate:.1f}%\n\n"

        answer += "💡 **建议**: 保持学习节奏，重点关注完成率较低的课程！"
        return answer

    def _format_learning_schedule_answer(self, results, current_date=None):
        """格式化学习安排查询结果"""
        if not results:
            return "📅 暂无近期学习安排。"

        answer = "📅 **近期学习安排:**\n\n"

        for row in results:
            if len(row) >= 3:
                course_content, online_learning_date, unit_number = row[:3]

                days_until = (online_learning_date - current_date).days if hasattr(online_learning_date,
                                                                                   'strftime') else '未知'

                answer += f"📖 **{course_content}** (单元: {unit_number})\n"
                answer += f"   📅 在线学习日期: {online_learning_date.strftime('%Y-%m-%d') if hasattr(online_learning_date, 'strftime') else online_learning_date}\n"
                if isinstance(days_until, int):
                    answer += f"   ⏰ 距离学习日期: {days_until}天\n\n"
                else:
                    answer += f"   ⏰ 距离学习日期: {days_until}\n\n"

        answer += "💡 **建议**: 请根据安排提前预习，合理分配学习时间！"
        return answer

    def _format_deadline_warning_answer(self, results, current_date=None):
        """格式化截止日期警告查询结果"""
        if not results:
            return "⏰ 目前没有即将到期的任务。"

        answer = "⏰ **即将到期任务提醒:**\n\n"

        for row in results:
            if len(row) >= 3:
                course_content, report_deadline, serial_number = row[:3]

                days_until = (report_deadline - current_date).days if hasattr(report_deadline, 'strftime') else '未知'
                urgency = '紧急' if isinstance(days_until, int) and days_until <= 3 else '即将到期'
                emoji = '🚨' if urgency == '紧急' else '⏰'

                answer += f"{emoji} **{course_content}** (序号: {serial_number})\n"
                answer += f"   📅 截止日期: {report_deadline.strftime('%Y-%m-%d') if hasattr(report_deadline, 'strftime') else report_deadline}\n"
                if isinstance(days_until, int):
                    answer += f"   ⏰ 剩余: {days_until}天\n\n"
                else:
                    answer += f"   ⏰ 剩余: {days_until}\n\n"

        answer += "💡 **建议**: 请优先完成紧急任务，避免逾期！"
        return answer

    def _format_peer_comparison_answer(self, results):
        """格式化同学比较查询结果"""
        if not results:
            return "📊 暂无可比较的班级数据。"

        answer = "📊 **与同学的比较:**\n\n"

        for row in results:
            if len(row) >= 4:
                rank, completed, avg_grade, total_students = row[:4]

                answer += f"🏅 **排名**: 第{rank}/{total_students}\n"
                answer += f"   ✅ 完成作业数: {completed}\n"
                answer += f"   📊 平均成绩: {avg_grade:.1f}\n\n"

        answer += "💡 **建议**: 继续努力，争取提升排名！"
        return answer

    def _format_resource_usage_answer(self, results):
        """格式化资源使用情况查询结果"""
        if not results:
            return "📚 您尚未访问任何学习资源。"

        answer = "📚 **学习资源使用情况:**\n\n"

        for row in results:
            if len(row) >= 6:
                resource_type, resource_name, access_count, total_seconds, avg_seconds, last_access = row[:6]

                hours = (total_seconds or 0) // 3600
                minutes = (total_seconds or 0) % 3600 // 60

                answer += f"📖 **{resource_name}** ({resource_type})\n"
                answer += f"   🔢 访问次数: {access_count}\n"
                answer += f"   ⏱️ 总时长: {hours}小时{minutes}分钟\n"
                answer += f"   ⏰ 平均每次: {int(avg_seconds or 0)}秒\n"
                answer += f"   📅 最后访问: {last_access.strftime('%Y-%m-%d %H:%M') if hasattr(last_access, 'strftime') else last_access}\n\n"

        answer += "💡 **建议**: 多利用优质资源如讲课视频和课件，提升学习效率！"
        return answer

    def _format_grade_inquiry_answer(self, results):
        """格式化成绩查询结果"""
        if not results:
            return "📝 暂无成绩记录。"

        answer = "📝 **您的成绩记录:**\n\n"

        for row in results:
            if len(row) >= 6:
                course_content, grade, submit_date, late_days, comments, grade_level = row[:6]

                emoji_map = {
                    '优秀': '🌟',
                    '良好': '👍',
                    '中等': '✅',
                    '及格': '✔️',
                    '不及格': '⚠️'
                }
                emoji = emoji_map.get(grade_level, '📝')

                answer += f"{emoji} **{course_content}**\n"
                answer += f"   📊 成绩: {grade:.1f} ({grade_level})\n"
                answer += f"   📅 提交日期: {submit_date.strftime('%Y-%m-%d') if hasattr(submit_date, 'strftime') else submit_date}\n"
                if late_days and late_days > 0:
                    answer += f"   ⏰ 迟交: {late_days}天\n"
                if comments:
                    answer += f"   💬 评语: {comments}\n\n"

        answer += "💡 **建议**: 关注成绩较低的课程，查看评语并改进！"
        return answer

    def _format_announcement_answer(self, results):
        """格式化公告查询结果"""
        if not results:
            return "📢 暂无有效的公告。"

        answer = "📢 **最新公告:**\n\n"

        for row in results:
            if len(row) >= 5:
                title, content, announcement_type, publish_date, expire_date = row[:5]

                emoji_map = {
                    '紧急': '🚨',
                    '截止提醒': '⏰',
                    '考试通知': '📝',
                    '一般通知': '📢'
                }
                emoji = emoji_map.get(row[5] if len(row) > 5 else announcement_type, '📢')

                answer += f"{emoji} **{title}** ({row[5] if len(row) > 5 else announcement_type})\n"
                answer += f"   💬 内容: {content}\n"
                answer += f"   📅 发布时间: {publish_date.strftime('%Y-%m-%d %H:%M') if hasattr(publish_date, 'strftime') else publish_date}\n"
                if expire_date:
                    answer += f"   ⏰ 有效期至: {expire_date.strftime('%Y-%m-%d') if hasattr(expire_date, 'strftime') else expire_date}\n\n"

        answer += "💡 **建议**: 请关注紧急和考试相关公告，及时采取行动！"
        return answer

    def _format_study_recommendation_answer(self, results):
        """格式化学习建议查询结果"""
        if not results:
            return "💡 您已完成所有任务，建议复习已学内容！"

        answer = "💡 **学习建议:**\n\n"

        for row in results:
            if len(row) >= 4:
                course_content, online_learning_date, report_deadline, priority = row[:3] + (
                    row[4] if len(row) > 4 else ['低优先级'])

                emoji_map = {
                    '高优先级': '🚨',
                    '中优先级': '⏰',
                    '低优先级': '✅'
                }
                emoji = emoji_map.get(priority, '💡')

                answer += f"{emoji} **{course_content}** ({priority})\n"
                answer += f"   📅 截止日期: {report_deadline.strftime('%Y-%m-%d') if hasattr(report_deadline, 'strftime') else report_deadline}\n"
                answer += f"   📚 建议: 尽快完成实验报告\n\n"

        answer += "💡 **建议**: 优先完成高优先级任务，合理安排时间！"
        return answer

    def _format_default_answer(self, results):
        """默认格式化方法，用于未定义的查询类型"""
        if not results:
            return "📋 暂无相关数据。"

        answer = "📋 **查询结果:**\n\n"

        for row in results:
            answer += f"📝 {', '.join(str(item) for item in row)}\n\n"

        answer += "💡 **建议**: 请检查问题表述或联系管理员获取更多信息！"
        return answer

    def _format_empty_result(self, query_type, question):
        """格式化空结果的通用方法"""
        default_messages = {
            QueryType.EXPERIMENT_REPORT: "📋 您目前没有未提交的实验报告，继续保持！",
            QueryType.UNIT_TEST: "📝 暂无即将进行的单元测试信息。",
            QueryType.COURSE_INFO: "📚 暂无课程信息。",
            QueryType.STUDENT_PROGRESS: "📈 暂无学习进度数据。",
            QueryType.LEARNING_SCHEDULE: "📅 暂无近期学习安排。",
            QueryType.DEADLINE_WARNING: "⏰ 目前没有即将到期的任务。",
            QueryType.TEACHER_FEEDBACK: "📝 暂时没有收到老师的反馈，请继续努力学习！",
            QueryType.LEARNING_ANALYTICS: "📊 暂无学习行为数据记录。",
            QueryType.PEER_COMPARISON: "📊 暂无可比较的班级数据。",
            QueryType.RESOURCE_USAGE: "📚 您尚未访问任何学习资源。",
            QueryType.GRADE_INQUIRY: "📝 暂无成绩记录。",
            QueryType.ANNOUNCEMENT: "📢 暂无有效的公告。",
            QueryType.STUDY_RECOMMENDATION: "💡 您已完成所有任务，建议复习已学内容！"
        }
        return default_messages.get(query_type, "📋 暂无相关数据，请尝试其他问题！")

    def _get_general_suggestions(self):
        """返回通用的问题建议"""
        return [
            "查看未提交的实验报告: '我有哪些作业没交？'",
            "查询成绩: '我的成绩怎么样？'",
            "获取教师反馈: '老师对我有什么反馈？'",
            "了解学习安排: '这周的学习计划是什么？'",
            "查看公告: '有什么重要通知？'"
        ]

    def get_conversation_suggestions(self, query_type):
        """根据查询类型返回后续对话建议"""
        suggestions_map = {
            QueryType.EXPERIMENT_REPORT: [
                "查看具体作业详情: '某课程的实验报告要求是什么？'",
                "查询截止日期: '我的作业什么时候到期？'",
                "获取学习建议: '我应该先完成哪些作业？'"
            ],
            QueryType.UNIT_TEST: [
                "查看测试详情: '单元测试的内容是什么？'",
                "获取复习建议: '如何准备单元测试？'",
                "查看课程进度: '我学到哪了？'"
            ],
            QueryType.COURSE_INFO: [
                "查看课程资源: '这门课有哪些学习资料？'",
                "查询学习安排: '课程什么时候开始？'",
                "获取教师反馈: '老师对这门课有什么建议？'"
            ],
            QueryType.STUDENT_PROGRESS: [
                "对比同学: '我和其他同学相比怎么样？'",
                "查看学习时间: '我花了多少时间学习？'",
                "获取改进建议: '我该如何提高进度？'"
            ],
            QueryType.LEARNING_SCHEDULE: [
                "查看具体课程: '下周要学什么？'",
                "查询截止日期: '最近有什么作业要交？'",
                "获取学习建议: '我应该怎么安排学习？'"
            ],
            QueryType.DEADLINE_WARNING: [
                "查看作业详情: '这些作业的具体要求是什么？'",
                "查询优先级: '哪些作业最紧急？'",
                "获取时间管理建议: '如何规划我的作业？'"
            ],
            QueryType.TEACHER_FEEDBACK: [
                "查看更多反馈: '最近的反馈有哪些？'",
                "查询成绩: '这门课的成绩怎么样？'",
                "获取改进建议: '我该如何改进？'"
            ],
            QueryType.LEARNING_ANALYTICS: [
                "查看资源使用: '我看了哪些学习资料？'",
                "对比同学: '我的学习时间和其他人比如何？'",
                "获取学习建议: '我该如何优化学习？'"
            ],
            QueryType.PEER_COMPARISON: [
                "查看详细进度: '我的具体进度如何？'",
                "查询成绩: '我的成绩排名如何？'",
                "获取提升建议: '我该如何提高排名？'"
            ],
            QueryType.RESOURCE_USAGE: [
                "查看课程资源: '有哪些推荐的学习资料？'",
                "查询学习时间: '我花了多少时间看资料？'",
                "获取使用建议: '我应该多看哪些资源？'"
            ],
            QueryType.GRADE_INQUIRY: [
                "查看教师评语: '老师对我的作业有什么评价？'",
                "查询作业状态: '我有哪些作业没交？'",
                "获取改进建议: '我该如何提高成绩？'"
            ],
            QueryType.ANNOUNCEMENT: [
                "查看紧急通知: '有什么紧急公告？'",
                "查询考试安排: '最近有什么考试？'",
                "获取课程更新: '课程有什么新消息？'"
            ],
            QueryType.STUDY_RECOMMENDATION: [
                "查看优先级任务: '我应该先完成什么？'",
                "查询学习资源: '有哪些推荐的学习资料？'",
                "获取时间规划: '我该如何安排学习时间？'"
            ]
        }
        return suggestions_map.get(query_type, self._get_general_suggestions())
